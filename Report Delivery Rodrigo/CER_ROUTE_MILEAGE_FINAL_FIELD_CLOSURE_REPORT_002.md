# CER Route — Route Mileage: cierre de campo
## Reporte 002

**Instrucción:** `CER_ROUTE_MILEAGE_FINAL_FIELD_CLOSURE_INSTRUCTIONS_002.md`
**Rama:** `fix/mileage-final-field-closure` (desde `dev`)
**Fecha:** 2026-10-06
**Continúa** `CER_ROUTE_MILEAGE_CROSS_SURFACE_DIAGNOSTIC_REPORT_001.md`. No reabre RTE06.

---

## 1. Resultado ejecutivo

**El cierre de campo no se puede proponer, y la razón no es técnica del producto: es de acceso.**

La instrucción dice en §4 que la autoridad de este cierre es el entorno compartido, y en §5 que los dos casos de campo no se pueden sustituir por datos sintéticos. Las dos cosas son correctas. Y ninguna de las dos la puedo ejecutar: desde este puesto no hay camino al entorno desplegado. Lo comprobé en vez de suponerlo, y la comprobación está en §2.

Lo que sí hice es todo lo que no dependía de ese acceso:

* **Determiné qué proveedor se selecciona en tiempo de ejecución y de dónde sale** — §4 del código, con el orden de precedencia exacto. §7 pedía no inferirlo de un reporte viejo; no lo inferí, lo leí.
* **Encontré que el camino de evidencia de §7 y §9 ya está construido.** El repositorio tiene un chequeo de plataforma `road_routing` que pide **una ruta real** y comprueba que la respuesta no es más corta que la línea recta, y otro `platform.scheduler` que mira el latido. Los ejecuté los dos aquí y dicen la verdad. CER puede producir la evidencia de §7 y §9 desde una pantalla, sin código nuevo, sin SQL y sin exponer la clave.
* **Medí qué va a encontrar CER en el caso A.** Con la evidencia intacta y ningún motor: `pending_calculation`, `attempt_count=1`, reintento programado hacia adelante y `last_error` = `No road routing engine is configured`. Eso no es una hipótesis, es una medición de este turno.
* **Entregué el trazador de campo** como comando de **sólo lectura**, para que la traza de §5 no se saque con SQL escrito a mano en una consola de producción.
* **Regresión de §16 verde**: 283 tests, 0 fallos, 0 errores, 15 saltados, todos `exit 0`.

Dos cosas que conviene leer aunque el resto esté ordenado:

* **Un test mío estaba mal y lo corregí en vez de corregir el producto.** Afirmé que un pendiente recién intentado debía salir como `VENCIDO`; la salida verdadera es `espera hasta <fecha>`, porque el reintento acotado se programa hacia adelante. El producto tenía razón. El test ahora cubre las dos ramas, y la distinción importa: confundirlas haría que un barrido detenido pareciera un pendiente sano.
* **No pedí credenciales por este canal y no las voy a pedir.** Un secreto que pasa por el chat queda quemado, y la del proveedor de routing ya lo está una vez (§13). La vía correcta es que la ejecución la haga quien ya tiene el acceso, con los comandos de §13.

**No es un `PARTIAL` sin explicar** (§19): el alcance que faltaba está nombrado, acotado a tres acciones concretas y cada una tiene su comando y su criterio de éxito.

---

## 2. Entorno compartido: identificado como inalcanzable desde aquí

§4 pide identificar el entorno. Lo que pude identificar es que **el que tengo configurado no es el compartido**:

| Comprobación | Resultado | Cómo |
|---|---|---|
| Base de datos configurada | `postgresql+asyncpg` · **`localhost:5432/cer_route`** | `make_url(settings.DATABASE_URL)`, imprimiendo sólo host/puerto/nombre |
| CLI de DigitalOcean | **no instalado** | `command -v doctl` |
| URL del despliegue | **no está en el repositorio** | los documentos sólo usan `<tenant>.<app-domain>` como plantilla |
| Credenciales del entorno desplegado | **ninguna disponible** | — |
| Lectura de `.env` | **denegada por el propio guardia de credenciales de la sesión** | se reporta tal cual; no se buscó una vía alterna |

Esa última fila es deliberada en las dos direcciones: no se leyó el archivo de secretos, y en su lugar se obtuvo el único dato que hacía falta —el host— por una vía que no materializa ninguna credencial.

**Identificación que corresponde a CER aportar** (§4), y que el comando de §13 imprime entero: `environment`, `tenant/company`, `supervisor`, `session_date`, `work_session_id`, `trip_id`, `trip_mileage_id`, `runtime routing provider`.

### Lo que hay en la base local, por si se dudaba de la premisa

No heredé esta premisa del reporte 001: la volví a medir.

```text
company                 : 1   (subdominio: cerroute)
user                    : 1
supervisor_profile      : 0
work_session            : 1
trip                    : 0      <- aquí muere el caso A y el caso B
trip_mileage            : 0
trip_mileage_segment    : 0
location_fix            : 0
missing_location_event  : 1
activity_execution      : 0
```

Hay una jornada y un evento sin ubicación sin ningún viaje detrás: residuo de una ejecución de pruebas, no datos de campo. **Cero viajes operativos**, así que no hay nada que trazar y §4 además prohíbe usar esta base como fuente final.

---

## 3. Traza del viaje afectado existente

`PENDING FIELD — no ejecutable desde este puesto.`

No la presento a medias ni la relleno con un viaje construido por mí: §5 lo prohíbe explícitamente y sería exactamente el tipo de evidencia que no vale.

**Lo que sí puedo dar es la clasificación esperada, medida.** Monté en local un viaje con la evidencia completa —dos waypoints `fresh`, `start_trip` y `arrived`— y dejé que el motor trabajara sin motor de carretera configurado, que es la situación del entorno compartido. Resultado medido:

```text
estado        : pending_calculation
attempt_count : 1
next_attempt_at: hacia adelante (reintento acotado programado)
last_error    : No road routing engine is configured (ROUTE_ROUTING_URL is empty).
total_meters  : null
terminal_reason: null
```

Eso es **`A2 — pending_calculation`, esperando al proveedor de routing**, según la taxonomía de §6. Y §6 dice «no aceptar un Pending indefinido»: no lo es. Es transitorio por diseño, con un camino automático a la resolución en cuanto el motor exista, y es la razón de que `UnconfiguredRouter` falle de forma **transitoria** en lugar de terminalizar viajes cuya evidencia está intacta.

Lo que esta predicción **no** descarta, y que CER tiene que comprobar con el comando de §13:

* que algún viaje esté en **`A4 — calculation_failed`** por haber agotado el reintento mientras no había motor. Ésos son terminales y el barrido **no** los recoge: se reponen con `reprocess_failed_mileage`, que ya existe. Está en §8.
* que algún viaje esté en **`A5 — sin registro de kilometraje`** habiendo llegado a `Arrived`. Eso sí sería un defecto de disparador o persistencia, y el comando lo imprime como `SIN REGISTRO`.
* que algún viaje esté en **`A3 — not_calculable`**. Si es así hay que leer la `terminal_reason`: el dominio distingue qué waypoint faltaba, no dice sólo «no calculable».

---

## 4. Proveedor de routing en tiempo de ejecución

§7 pedía determinar qué está activo **ahora** y no inferirlo. El orden de precedencia es éste, leído del código (`app/routers_api/mileage/routing.py`, `_construir()` y `_desde_la_integracion()`):

```text
1. integración de plataforma `road_routing`, si está habilitada y con proveedor
      tomtom   -> exige el secreto `api_key`; sin él NO se monta y se registra
                  un aviso: un adaptador que no puede responder no se instala
      osrm     -> exige `base_url`; usa el snap radius de la política
      valhalla -> exige `base_url`
2. si no: ROUTE_ROUTING_URL  (+ ROUTE_ROUTING_FALLBACK_URL -> OSRM con reserva Valhalla)
3. si no: UnconfiguredRouter -> falla TRANSITORIO a propósito
```

Dos propiedades que importan para el diagnóstico de CER:

* **No hay caché.** El adaptador se construye en cada llamada, así que un cambio en la pantalla de integraciones surte efecto **sin desplegar ni reiniciar**. Ésa es la vía rápida.
* **Una integración a medio configurar no deja el sistema mudo.** Si `road_routing` selecciona TomTom y falta la clave, devuelve `None` y se cae al camino de entorno, dejando el aviso en el registro. Es decir: *«seleccionado pero sin credencial»* no se confunde con *«no configurado»*.

### Medido en este entorno

```text
adaptador seleccionado : unconfigured  (UnconfiguredRouter)
chequeo road_routing   -> not_applicable
   "No routing engine is configured, so trip mileage stays pending."
```

Aplica **sólo a local**. Local no es compartido.

### El camino de evidencia de §7, que ya existe

El chequeo `road_routing` de la plataforma hace exactamente lo que §7 enumera, y lo hace mejor que un ping:

| §7 pide | El chequeo lo da |
|---|---|
| proveedor/adaptador seleccionado | el nombre del adaptador en el detalle |
| fuente de configuración | la precedencia de §4 lo determina |
| ¿habilitado? ¿secreto presente? | si falta la clave no se monta y el detalle lo dice |
| conectividad | petición real, con timeout |
| **una petición de ruta real** | Times Square → Bryant Park |
| distancia vial devuelta | en el detalle |
| error del proveedor, si hay | clasificado **transitorio** (`unreachable`) vs **permanente** (`auth_failed`) |

Y comprueba lo único que no se puede falsear: **por carretera no se puede ir menos que en línea recta**. Si alguien invirtió latitud y longitud, o si el motor auto-alojado tiene cargado un extracto de otra región, la relación se rompe y el chequeo lo marca `degraded` en vez de dar un `200 OK` con una distancia de otro continente. Ése es el modo de fallo que no rompe nada y miente, y es el que esta comprobación está diseñada para cazar.

**La clave no sale en ningún mensaje.** El adaptador de TomTom redacta la clave de todo texto que vaya a un error, porque ese texto acaba en `trip_mileage.last_error`, que se conserva.

---

## 5. Ejecución de routing real

`PENDING FIELD.` §8 exige una ruta real **con extremos capturados de un viaje real**, y no tengo ni motor en el entorno compartido ni viajes.

Lo que está en pie, y es relevante para no confundir un hueco de entorno con un defecto de adaptador:

* **El adaptador ya se midió contra un motor real** en RTE06: `osrm/osrm-backend` con el extracto de Mónaco del propio proyecto OSRM, con `ROUTE_ROUTING_URL=http://localhost:5000`. Está certificado y §3 dice no reabrirlo, así que no lo reabrí.
* **El suite de motor real existe y está en la regresión**: `tests/integration/test_route_routing_live.py`, 15 tests. **14 se saltaron** por `sin ROUTE_ROUTING_URL no hay motor primario que medir`, y 1 más en el motor de kilometraje por la misma puerta. Esos 15 saltos son la forma exacta que tiene este hueco en la regresión: no están rotos, están esperando un motor.

Deliberadamente **no** llamé a un servicio de routing público para fabricar una ejecución «real»: no habría cerrado nada de §8 —los extremos no serían de un viaje real ni el entorno sería el compartido— y sólo habría vuelto a probar lo que RTE06 ya certificó.

---

## 6. Persistencia de TripMileage

Las columnas que §6 pide inspeccionar existen todas, y el comando de §13 las imprime:

```text
trip_mileage          : id, company_id, trip_id, state, total_meters, calculated_at,
                        terminal_reason, attempt_count, next_attempt_at, last_error
trip_mileage_segment  : sequence, from_event_kind, to_event_kind, distance_meters,
                        provider, method, provider_version, haversine_meters,
                        from/to_evidence_level, from/to_accuracy_m, from/to_captured_at
```

La procedencia (`provider` / `method` / `provider_version`) se guarda **por tramo**, no por viaje, que es lo que permite auditar una distancia años después. Y cada tramo conserva además su `haversine_meters`, de modo que la comprobación de plausibilidad sigue siendo verificable a posteriori sobre la fila guardada.

Verificado de punta a punta en local con el motor sustituido por uno de distancia conocida: 20 000 m por tramo → `state=calculated`, `total_meters=20000.00`, un tramo con `proveedor=fijo/test/1`, y 12,4 millas publicadas. 20 000 m son 12,4274 mi; se eligió un número que **no** es redondo en millas justamente para que un error de conversión o de redondeo se vea.

---

## 7. Reintento y barrido

`PENDING FIELD` para la ejecución en el entorno compartido. Mecánica verificada aquí.

Lo registrado en el código:

* el barrido está **registrado en el scheduler que ya existe**, no en uno nuevo: `register_route_jobs()` → `platform_scheduler.register("route_location_mileage_sweep", ...)`, con disparador de intervalo;
* el intervalo sale de la política `route_mileage.sweeper_interval_minutes`, **ajustable sin desplegar**;
* corre **sólo en la instancia líder**, así que con varias instancias no se duplica;
* hace **dos** barridos en un orden deliberado: primero cierra las ventanas de ubicación vencidas y después empuja el kilometraje pendiente. Al revés, el segundo gastaría un intento del reintento acotado en viajes cuya evidencia el primero está a punto de declarar perdida;
* un fallo del primero no impide el segundo.

Medido en este turno: el barrido avanzó `attempt_count` a 1, dejó el estado en `pending_calculation` y escribió la causa en `last_error`. Y el trazador distingue las dos situaciones que §9.8 exige poder distinguir:

| Situación | Lo que imprime |
|---|---|
| Reintento programado hacia adelante | `espera hasta <fecha>` |
| Reintento ya vencido y el registro sigue ahí | `VENCIDO (el barrido debe recogerlo)` |

Esa segunda línea es el diagnóstico de «el barrido no está corriendo», y es la que convierte §9.8 —*«Pending no se queda indefinidamente porque el job no corre»*— en algo observable desde una consola.

**El camino de evidencia de §9 también existe ya**: el chequeo `platform.scheduler` compara el último latido contra el reloj. Ejecutado aquí:

```text
platform.scheduler -> degraded
   "The last scheduler heartbeat was 155 minutes ago."
```

Correcto: en este puesto no hay scheduler corriendo. En el entorno compartido ese mismo chequeo debe devolver `healthy` / *«The scheduler is running»*, y si devuelve `degraded` o `not_applicable` entonces §9.8 es el diagnóstico y no hay que buscar más lejos.

Y la línea de registro que CER puede buscar en los registros del despliegue es literalmente `ROUTE SWEEP |`, con `missing_finalized=` y el resumen del kilometraje. §9 permite usar el estado de la base antes y después del intervalo cuando el registro no alcanza; con esa línea, alcanza.

---

## 8. Comportamiento del atraso

`PENDING FIELD.` La clasificación la produce `--pending` del comando de §13, que agrupa por estado y, para cada pendiente, dice si está vencido y por qué sigue ahí.

Lo que está decidido de antemano y CER debe saber antes de mirar:

| Estado encontrado | Se resuelve solo cuando aparezca el motor | Acción |
|---|---|---|
| `pending_calculation` | **sí** | ninguna; el barrido lo recoge |
| `calculation_failed` | **no**, es terminal | `reprocess_failed_mileage` con rango de fechas |
| `not_calculable` | **no**, y es correcto | ninguna: falta evidencia, y no se inventa |
| sin registro | — | defecto de disparador; hay que corregirlo |

El segundo caso es el que puede sorprender, y es una decisión de diseño, no un olvido: el barrido sólo recoge `pending_calculation`. Un estado terminal que se reabriera solo no sería terminal. Pero eso significa que **desplegar el motor no recupera por sí mismo** los viajes que ya agotaron el reintento mientras no lo había, y por eso existe el comando explícito —con simulación por omisión y `--aplicar` para escribir—. Reabrir un hecho ya terminalizado es una decisión de negocio.

§10 pide probar que el producto **no** necesita una corrección manual por viaje para una recuperación normal del proveedor. Para `pending_calculation` está probado: el barrido lo hace solo. Para `calculation_failed` hay **un** comando por rango de fechas, no una corrección por viaje — y que exista es la consecuencia de una semántica certificada, no un defecto.

---

## 9. Today / Live — evidencia de campo

`PENDING FIELD` para el viaje real. La cadena de lectura está verde en regresión.

```text
TripMileage.total_meters        20000.00
  -> /api/live/today            official_miles del supervisor
  -> summary                    total_miles
  -> navegador, escritorio      12.4
  -> navegador, móvil           12.4
```

Verificado con `tests/integration/test_live_today.py` (15/15) y `tests/e2e/test_mileage_cross_surface_browser.py` (4/4, navegador real, escritorio y móvil). Cubierto además: el supervisor correcto, el día de negocio correcto, sin fuga entre supervisores y sin fuga entre tenants.

Lo que falta es exclusivamente que la cifra la produzca un viaje real del entorno compartido. La superficie que la muestra ya está demostrada.

---

## 10. Activity Explorer — evidencia de campo

`PENDING FIELD` para el viaje real. Cadena de lectura verde.

```text
TripMileage.total_meters
  -> /api/activity-explorer     summary.official_miles
  -> resumen del día            12.4
  -> agregados semana/mes/año
```

Y el punto que §12 marca como importante está probado explícitamente: **un viaje puede aportar millas al total del día sin tener tarjeta de actividad**. El explorador lista **paradas** —bloques de ejecución—, no viajes; un viaje que llegó y no ejecutó nada suma sus millas y no dibuja tarjeta. Eso es correcto y no es kilometraje perdido. `tests/integration/test_activity_explorer.py` 17/17 y el suite cross-surface lo fijan.

---

## 11. Consistencia entre superficies

**Verde, por regresión.** `tests/integration/test_mileage_cross_surface.py`, 8/8:

```text
                 Millas oficiales (un solo hecho)
                            │
             ┌──────────────┴──────────────┐
        Today / Live                Activity Explorer
             12.4                         12.4
```

* `test_las_dos_superficies_son_el_mismo_hecho` — no hay dos fórmulas;
* `test_un_calculo_pendiente_no_se_presenta_como_cero_final` — Pending no es cero final;
* `test_un_viaje_sin_evidencia_no_fabrica_millas` — sin evidencia no hay número;
* `test_dos_viajes_calculados_suman_en_las_dos_superficies` — el agregado coincide;
* `test_el_kilometraje_se_queda_en_su_dia_de_negocio` — las millas no aparecen en el día natural siguiente;
* `test_las_millas_de_un_supervisor_no_pasan_a_otro` y `test_las_millas_de_un_tenant_no_pasan_al_otro`.

Reports queda fuera: no está implementado (§13).

---

## 12. Correcciones aplicadas

**`NO PRODUCT CODE CHANGE`.** Ningún archivo del producto cambió: ni el motor de kilometraje, ni el adaptador de routing, ni el barrido, ni el modelo de lectura, ni la API, ni el frontend. No se demostró ningún defecto que lo justificara, y §15 sólo autoriza corregir con evidencia de campo que lo pruebe.

Lo que se añadió es **una herramienta de ejecución, de sólo lectura**, para poder hacer el cierre que esta instrucción pide:

| Archivo | Líneas | Qué es |
|---|---:|---|
| `app/db/scripts/trace_trip_mileage.py` | 344 | el trazador. **Sólo lee**: no hay `commit`, ni `UPDATE`, ni `--aplicar` |
| `tests/integration/test_trace_trip_mileage.py` | 231 | 6 tests sobre un viaje calculado de verdad |

No es un añadido de observabilidad al producto —§9 pide no meter uno salvo que no haya otra forma, y sí la hay—: no lo importa la aplicación, no corre en ningún proceso y se puede borrar sin tocar nada. Existe porque la alternativa es SQL escrito a mano en una consola de producción, donde un `UPDATE` queda a un carácter de distancia de un `SELECT`.

Tres decisiones que vale la pena nombrar:

* **Las coordenadas no salen por omisión.** La traza necesita saber si un waypoint **existe** y con qué nivel de evidencia, no dónde estaba la persona. Por omisión imprime `presente nivel=fresh ±10m @<hora>`; `--coordenadas` las muestra, y esa salida ya no debe pegarse en un documento. Hay un test para cada rama, de modo que el control de privacidad no puede quedarse en una promesa del docstring.
* **Que no escriba está probado por mutación, no afirmado.** El test fotografía `trip_mileage` entera y el contador de `audit_event` antes y después de las tres salidas. Para comprobar que esa foto detecta algo, le inyecté al comando un `UPDATE trip_mileage SET attempt_count = attempt_count + 1`: el test **falló**. Revertido, 6/6 verde y cero ocurrencias de `UPDATE` en el archivo.
* **Reutiliza la preparación del suite cross-surface** en vez de copiar 120 líneas de montaje real —supervisor, vehículo, jornada, odómetro, viaje, actividad, dos puntos de ubicación—, que es lo que se habría separado del dominio con el primer cambio.

### Un defecto mío, y cómo se resolvió

El quinto test afirmaba que un pendiente recién intentado debía imprimirse como `VENCIDO`. Falló, y la salida real era la correcta:

```text
viaje 1: intentos=1 espera hasta 2026-10-06 22:09:23+00:00
  ultimo error: No road routing engine is configured (ROUTE_ROUTING_URL is empty).
```

El reintento acotado se programa **hacia adelante**: el producto tenía razón y mi aserción estaba mal. Corregí el test —no el producto— y lo amplié para cubrir las dos ramas, venciendo el reintento y comprobando que entonces sí dice `VENCIDO`. La distinción no es cosmética: es la que separa un pendiente sano de un barrido detenido.

---

## 13. Acciones de DevOps / entorno

Tres acciones, en este orden. Las tres en el **entorno compartido**; nada de lo de este reporte las hace.

### A — Configurar el motor de carretera

Es la que desbloquea todo lo demás. Dos caminos soportados:

**A1 · Integración de plataforma (en caliente, sin desplegar)** — `/admin/platform/settings`, integración `Road routing engine`, proveedores `osrm` / `valhalla` / `tomtom`. El adaptador se reconstruye en cada llamada, así que surte efecto de inmediato.

> **Si se elige TomTom, rotar primero la clave.** La actual pasó por el chat y está quemada. Rotar, guardar la nueva **por el endpoint de secretos** —que la cifra con la llave maestra—, nunca en el campo de configuración: la validación rechaza un secreto enviado como configuración justamente para que no quede en claro.

**A2 · Variables de entorno (motor auto-alojado, exige desplegar)**

```text
ROUTE_ROUTING_URL=http://<osrm>:5000
ROUTE_ROUTING_FALLBACK_URL=http://<valhalla>:8002   # opcional, activa la reserva
```

Con un extracto OSM que **cubra la región de operación de CER**. Un extracto de otra región responderá `NoSegment` y el kilometraje terminalizará diciendo la verdad — correcto, pero inútil.

### B — Verificar, desde la pantalla

`/admin/platform/diagnostics` (requiere administrador de plataforma), ejecutar:

| Chequeo | Criterio de éxito |
|---|---|
| `road_routing` | **`healthy`** + *«\<motor\> answered N m … for a known M m straight line»* |
| `platform.scheduler` | **`healthy`** + *«The scheduler is running»* |

Y la lectura de los fallos, para no diagnosticar a ciegas:

* `not_applicable` → no hay motor seleccionado. La acción A no surtió efecto.
* `unreachable` → seleccionado pero no responde. **`ENVIRONMENT / DEVOPS REACHABILITY`** (§7): red, firewall o contenedor caído.
* `auth_failed` → respondió y rechazó. Clave inválida o petición no aceptada.
* `degraded` con *«which is impossible by road»* → responde pero **miente**: extracto de otra región, o latitud/longitud invertidas en una configuración.

### C — Clasificar los viajes reales y cerrar el atraso

```bash
# 1. Qué hay, y en qué estado
uv run python -m app.db.scripts.trace_trip_mileage --company cerroute --recent 50

# 2. El atraso: qué espera reintento, qué está vencido y por qué
uv run python -m app.db.scripts.trace_trip_mileage --company cerroute --pending

# 3. La traza completa del viaje afectado (caso A) y del nuevo (caso B)
uv run python -m app.db.scripts.trace_trip_mileage --trip <ID>

# 4. Sólo si aparecen `calculation_failed`: simulación primero
uv run python -m app.db.scripts.reprocess_failed_mileage --company cerroute \
    --desde <YYYY-MM-DD> --hasta <YYYY-MM-DD>
# y después, con el motor ya verificado en B:
#   ... --aplicar
```

El paso 1 y el 2 no escriben nada. El 4 escribe sólo con `--aplicar`.

**La salida del paso 3 es la traza que §18 pide**, con la jornada, el viaje, cada waypoint con su nivel de evidencia, el estado del kilometraje, los intentos, el proveedor por tramo y los metros. Por omisión **sin coordenadas**, de modo que se puede pegar en el reporte de certificación.

### Acciones de entregas anteriores, todavía abiertas

No son de este alcance; se listan para que no se pierdan:

1. `uv run python -m app.db.scripts.align_role_capabilities` (RTE07 / RTE08)
2. `BOOTSTRAP_COMPANY_SUBDOMAIN=cerroute` — y **no** ejecutar `bootstrap` sin ella: crearía una compañía `cer` nueva
3. `TESSDATA_PREFIX=/layers/digitalocean_apt/apt/usr/share/tesseract-ocr/4.00/tessdata`
4. `ODOMETER_PHOTO_RETENTION_MINUTES=60`
5. Restringir las *Trusted Sources* de la base (hoy abierta a internet)
6. Quitar el `exit 0` de la especificación de migraciones

---

## 14. Regresión

**283 tests · 0 fallos · 0 errores · 15 saltados · todos `exit 0`.** Por lotes separados: mezclar módulos en una sola invocación dispara una fragilidad preexistente del arnés (`fixture 'seeded' not found`), ya clasificada y reproducida con archivos de `dev`.

| Lote | Tests | Fallos | Err | Skip | Exit | Seg |
|---|---:|---:|---:|---:|---:|---:|
| `test_trace_trip_mileage.py` (nuevo) | 6 | 0 | 0 | 0 | 0 | 29 |
| `test_route_mileage_engine.py` | 24 | 0 | 0 | **1** | 0 | 38 |
| `test_route_routing_live.py` | 15 | 0 | 0 | **14** | 0 | 11 |
| `test_road_routing_wiring.py` | 8 | 0 | 0 | 0 | 0 | 6 |
| `test_tomtom_router.py` | 13 | 0 | 0 | 0 | 0 | 6 |
| `test_reprocess_failed_mileage.py` | 5 | 0 | 0 | 0 | 0 | 20 |
| `test_route_location_evidence.py` | 39 | 0 | 0 | 0 | 0 | 69 |
| `test_trips.py` | 66 | 0 | 0 | 0 | 0 | 143 |
| `test_live_today.py` | 15 | 0 | 0 | 0 | 0 | 68 |
| `test_mileage_cross_surface.py` | 8 | 0 | 0 | 0 | 0 | 58 |
| `test_activity_explorer.py` | 17 | 0 | 0 | 0 | 0 | 71 |
| `test_permission_catalog.py` | 7 | 0 | 0 | 0 | 0 | 14 |
| `test_public_surface.py` | 14 | 0 | 0 | 0 | 0 | 17 |
| `test_page_wiring.py` | 33 | 0 | 0 | 0 | 0 | 10 |
| `test_navigation_wiring.py` | 9 | 0 | 0 | 0 | 0 | 12 |
| `test_mileage_cross_surface_browser.py` (navegador real) | 4 | 0 | 0 | 0 | 0 | 79 |

**Los 15 saltos son el hueco de este cierre, no un fallo.** Todos tienen la misma puerta: `sin ROUTE_ROUTING_URL no hay motor real que medir`. En cuanto la acción A de §13 esté hecha, dejan de saltarse.

* `import app.main` → **ok**
* Migraciones → **NOT APPLICABLE** (sin cambio de esquema)
* Frontend `npm run check` → **NOT APPLICABLE** (ningún archivo de interfaz cambió)
* Lint de Python → **NOT APPLICABLE**: el repositorio no tiene linter de Python configurado (`ruff` no está instalado y no hay `[tool.ruff]`). Lo que sí se ejecutó: `import app.main`, las cuatro redes de cableado y finales de línea LF verificados.

---

## 15. Esperado → Implementado → Evidencia → Hueco

### Escenarios de campo de §14

| FC | Escenario | Estado | Evidencia |
|---|---|---|---|
| FC-01 | Viaje afectado existente, clasificado | **PENDING FIELD** | §3; clasificación esperada **medida** (`A2`), falta el viaje real |
| FC-02 | Viaje nuevo llega a `calculated` | **PENDING FIELD** | §5; bloqueado por la acción A de §13 |
| FC-03 | Today / Live lo muestra | **PENDING FIELD** | §9; camino de lectura verde (15/15 + 4/4 navegador) |
| FC-04 | Activity lo muestra | **PENDING FIELD** | §10; camino de lectura verde (17/17 + 8/8) |
| FC-05 | Recuperación de un pendiente | **PENDING FIELD** | §7; mecánica medida (`attempt_count` 0→1, rama `VENCIDO`) |
| FC-06 | Sin evidencia no se fabrican millas | **PASS** (regresión; no observado en campo) | `test_un_viaje_sin_evidencia_no_fabrica_millas` |
| FC-07 | Varios viajes agregan | **PASS** (regresión; no observado en campo) | `test_dos_viajes_calculados_suman_en_las_dos_superficies` |
| FC-08 | Día de negocio, incluido cruce de medianoche | **PASS** | `test_el_kilometraje_se_queda_en_su_dia_de_negocio`; §14 autoriza regresión aquí |
| FC-09 | Aislamiento entre tenants | **PASS** (regresión; no observado en campo) | `test_las_millas_de_un_tenant_no_pasan_al_otro` + supervisor |

Los cinco `PENDING FIELD` no se presentan como `PASS` en ninguna forma: la evidencia ausente no se convierte en evidencia.

### Criterios de aceptación de §17

| # | Criterio | Estado |
|---:|---|---|
| 1 | Un viaje afectado real trazado | **PENDING FIELD** |
| 2 | Su causa/estado real conocido | **PENDING FIELD** (clasificación esperada medida, §3) |
| 3 | Proveedor del entorno compartido identificado | **PENDING FIELD** (precedencia y camino de verificación, §4) |
| 4 | Una petición de ruta real con éxito | **PENDING FIELD** |
| 5 | Un viaje real llega a `calculated` | **PENDING FIELD** |
| 6 | `total_meters` positivo persistido | **PENDING FIELD** (persistencia verificada en local, §6) |
| 7 | Today / Live muestra las millas correctas | **VALIDATED** en el camino de lectura · **PENDING FIELD** con dato real |
| 8 | Activity muestra/agrega correctamente | **VALIDATED** en el camino de lectura · **PENDING FIELD** con dato real |
| 9 | Las dos superficies usan el mismo hecho | **VALIDATED** (§11) |
| 10 | Reintento/barrido funciona en el compartido | **PENDING FIELD** (mecánica y camino de evidencia, §7) |
| 11 | El atraso elegible puede avanzar solo | **VALIDATED** para `pending_calculation` · comando para `calculation_failed` (§8) |
| 12 | La evidencia ausente no fabrica millas | **VALIDATED** (FC-06) |
| 13 | Semántica del día de negocio correcta | **VALIDATED** (FC-08) |
| 14 | Aislamiento entre tenants correcto | **VALIDATED** (FC-09) |
| 15 | Sin reserva de odómetro ni Haversine | **VALIDATED** — la reserva es **otro motor de routing**; Haversine sólo se guarda como control de plausibilidad |
| 16 | Regresión afectada verde | **VALIDATED** (§14) |
| 17 | Sin Pending inexplicado en los casos controlados | **VALIDATED** — el único Pending local está explicado y es transitorio por diseño |
| 18 | Sin `PARTIAL`/`GAP`/`BLOCKED`/decisión pendiente | **el hueco está nombrado y acotado**, §16 |

---

## 16. Asuntos restantes

**Un solo hueco, y es de acceso al entorno, no de producto:**

```text
hecho        La autoridad de este cierre es el entorno compartido (§4) y los dos
             casos de campo no admiten datos sintéticos (§5). Desde este puesto
             no hay camino a ese entorno: la base configurada es
             localhost:5432/cer_route, no hay doctl, no hay URL desplegada y no
             hay credenciales.

impacto      FC-01 a FC-05 y los criterios 1-6 y 10 de §17 no se pueden
             producir aquí. Todo lo que no dependía de ese acceso está hecho y
             verde.

opciones     1. CER / DevOps ejecuta las tres acciones de §13 y aporta la salida
                de los dos chequeos y de las tres trazas. Development redacta el
                cierre con esa evidencia.
             2. Se habilita a Development un acceso de sólo lectura al entorno
                compartido —por la vía de operaciones, nunca por el chat— y lo
                ejecuta directamente.
             3. No hacer nada: el kilometraje sigue `pending_calculation` para
                siempre en campo. Veraz, e inservible.

recomendada  La 1. El camino de evidencia ya está construido: dos chequeos desde
             una pantalla y tres comandos de sólo lectura. No hace falta acceso
             nuevo, ni código, ni SQL, ni exponer la clave. Y la 2 implica mover
             una credencial de producción, que es un riesgo mayor que el
             problema que resolvería.
```

**Esto no es una decisión de producto pendiente**, así que no se declara `BLOCKED — CER DECISION REQUIRED`: ninguna regla de §3 entró en conflicto con la evidencia y no hay nada que redefinir. Es trabajo operativo con dueño, comando y criterio de éxito.

**Deuda preexistente, declarada**: la fragilidad del arnés de §14 y las seis acciones de entregas anteriores de §13.

---

## 17. Estado propuesto

```text
ROUTE MILEAGE FIELD CLOSURE NOT PROPOSABLE
  — SHARED-ENVIRONMENT ROUTING CONFIGURATION AND FIELD TRACE REQUIRED (§7, §13)
```

**No se declara** `ROUTE MILEAGE FIELD CLOSURE COMPLETE / READY FOR CER CERTIFICATION`: §19 lo permite sólo con toda la evidencia obligatoria en verde, y faltan cinco escenarios de campo. **No se declara** `ROUTE MILEAGE CLOSED`: la certificación es de CER. **Y no se declara** `BLOCKED — CER DECISION REQUIRED`: no hay ninguna decisión de producto pendiente.

Lo entregado, que es real: la precedencia del proveedor leída del código; el camino de evidencia de §7 y §9 identificado y **ejecutado** aquí; la clasificación esperada del caso A **medida**; el trazador de campo de sólo lectura, probado por mutación; y la regresión en verde.

---

## 18. Estimación del esfuerzo

| Componente | Líneas |
|---|---:|
| `app/db/scripts/trace_trip_mileage.py` | 344 |
| `tests/integration/test_trace_trip_mileage.py` | 231 |
| **Total** | **575 / −0** |

| Tarea | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Determinar el acceso real al entorno compartido | `DONE` | — | diagnóstico | 0,5 |
| Estado de la base de primera mano, sin heredar premisas | `DONE` | — | diagnóstico | 0,3 |
| Leer la precedencia del proveedor y los dos chequeos | `DONE` | ~500 LoC leídas | análisis | 0,8 |
| Ejecutar `road_routing` y `platform.scheduler` aquí | `DONE` | — | integración | 0,4 |
| Medir la clasificación esperada del caso A | `DONE` | — | integración | 0,5 |
| Trazador de sólo lectura | `DONE` | ~344 LoC | backend | 2,0 |
| 6 tests, mutación incluida | `DONE` | ~231 LoC | integración | 2,4 |
| Corregir mi aserción equivocada y cubrir las dos ramas | `DONE` | — | diagnóstico | 0,3 |
| Regresión por lotes (283 tests, navegador incluido) | `DONE` | 16 lotes | ejecución | 1,1 |
| Reporte 002 | `DONE` | — | documentación | 0,9 |
| **Subtotal ejecutado** | | | | **9,2** |
| Margen de riesgo (+30%, depende de proveedor de terceros) | | | | **+2,8** |
| **Total del delta** | | | | **≈ 12,0 h-agente** |

### Lo que falta, estimado

| Tarea | Dueño | Horas |
|---|---|---|
| Configurar el motor (A1 en caliente, o A2 con despliegue) | CER / DevOps | 0,5 – 3,0 |
| Rotar la clave de TomTom, si se elige ese camino | CER | 0,3 |
| Ejecutar los dos chequeos y las tres trazas | CER | 0,5 |
| Redactar el cierre con la evidencia de campo | Development | 1,5 |
| Reponer `calculation_failed`, si aparecen | Development | 0,5 |
| **Total hasta `FIELD CLOSURE COMPLETE`** | | **≈ 3,3 – 5,8** |

El rango de la primera fila es real y no es imprecisión: por la integración de plataforma son minutos; levantar un OSRM auto-alojado con el extracto de la región correcta es otra cosa.

---

## 19. Siguiente paso

Ejecutar la acción **A** de §13 en el entorno compartido y después la **B**. Con los dos chequeos en `healthy` y la salida de las tres trazas, Development redacta el cierre de campo.

**No se inicia RTE09. No se reanuda RTE10-A01. No se rediseña Today / Live ni Activity Explorer.** A la espera de la revisión y certificación de CER.
