# CER Route — Diagnóstico de kilometraje entre superficies
## Reporte 001

**Instrucción:** `CER_ROUTE_MILEAGE_CROSS_SURFACE_DIAGNOSTIC_INSTRUCTIONS_001.md`
**Rama:** `fix/mileage-cross-surface-diagnostic` (desde `dev`)
**Fecha:** 2026-10-06

---

## 1. Resultado ejecutivo

**No hay ningún defecto de producto.** Las millas no se ven porque **no
existen**: en este entorno no hay motor de carretera configurado, así que
ningún viaje puede llegar a `calculated`.

La cadena completa está probada y correcta. Con un motor que devuelve una
distancia conocida, **20 000 m llegan como `12.4 mi` idénticos** a:

```text
TripMileage.total_meters = 20000
        ├── GET /api/live/today        official_miles = "12.4"  total_miles = "12.4"
        ├── Today / Live, pantalla     12.4   (escritorio y móvil)
        ├── GET /api/activity-explorer resumen = "12.4"  parada = "12.4"
        ├── Activity Explorer, pantalla 12.4 mi
        └── agregados semana/mes/año   "12.4"
```

Persistencia, modelo de lectura, API y pantalla: ninguna capa pierde la cifra.
No eran tres defectos de interfaz, y no era uno compartido.

**Lo que sí hay** es un bloqueo de entorno, demostrado en ejecución y no
deducido de un reporte viejo:

```text
ROUTE_ROUTING_URL          : ''
integración road_routing   : NO EXISTE
ADAPTADOR ACTIVO           : UnconfiguredRouter
```

**Un límite de este diagnóstico, por delante.** §5 pide trazar un viaje real
del tenant actual. **No pude**: la base de desarrollo a la que tengo acceso
tiene **0 viajes** —la compañía `cerroute` está sembrada pero sin datos
operativos— y los registros afectados viven en el entorno compartido, al que no
llego. Lo que entrego en su lugar es la ejecución **real del pipeline** en este
entorno más las consultas exactas para clasificar los viajes de campo (§3).

---

## 2. El síntoma, reproducido

Un viaje completo por el camino del producto —jornada, odómetro resuelto,
viaje, salida, llegada— y después el barrido, como lo correría el scheduler:

```text
ADAPTADOR ACTIVO: UnconfiguredRouter
START : 200      ARRIVE : 200
trip_mileage     -> 1 fila, state=pending_calculation, meters=None, intentos=0
barrido 1        -> examined=1, pending_calculation=1
                    err = "Waiting for location evidence"
```

Y con la evidencia de ubicación entregada, el bloqueo **cambia**:

```text
evidencia start_trip: 201     evidencia arrived: 201
barrido 1 -> err = "No road routing engine is configured (ROUTE_ROUTING_URL is empty)."
             state = pending_calculation
```

Son **dos bloqueos en serie**, y separarlos importa porque llevan a acciones
distintas. El primero es de datos de campo; el segundo, de entorno.

---

## 3. Traza del viaje real — **PENDING**, y por qué

| Elemento | Estado |
|---|---|
| Tenant | `cerroute` presente en la base local |
| Viajes (`trip`) | **0** |
| `trip_mileage` | **0** |
| `location_fix` | **0** |
| `supervisor_profile` | **0** |

No hay un viaje real que trazar aquí. **No se inventa uno** y no se presenta un
sintético como si lo fuera.

Para que CER —o yo, con acceso a la base compartida— complete D1 y D2 sin
adivinar, estas son las consultas que producen la clasificación de §D2 tal cual:

```sql
-- D1: viajes de un supervisor y un día de negocio
SELECT c.subdomain, ws.session_date, ws.id AS work_session_id, ws.user_id,
       t.id AS trip_id, t.status, t.current_purpose,
       t.started_at IS NOT NULL AS salio,
       t.arrived_at IS NOT NULL AS llego,
       t.ended_at  IS NOT NULL AS cerro
FROM trip t
JOIN work_session ws ON ws.id = t.work_session_id
JOIN company c       ON c.id = t.company_id
WHERE c.subdomain = 'cerroute' AND ws.session_date = DATE '____-__-__'
ORDER BY t.id;

-- D2: la fila de kilometraje y su clasificación en ramas A..E
SELECT tm.trip_id, tm.state, tm.total_meters, tm.attempt_count,
       tm.next_attempt_at, tm.terminal_reason, tm.calculated_at,
       left(tm.last_error, 120) AS ultimo_error,
       (SELECT count(*) FROM trip_mileage_segment s
         WHERE s.trip_mileage_id = tm.id) AS tramos
FROM trip_mileage tm
WHERE tm.trip_id IN ( /* los de arriba */ );

-- D3: la evidencia de waypoint que el motor exige
SELECT event_kind, subject_id, evidence_level, captured_at
FROM location_fix
WHERE company_id = (SELECT id FROM company WHERE subdomain = 'cerroute')
ORDER BY captured_at;
```

Predicción, para que se pueda **falsar**: si no se ha configurado motor de
carretera, todas las filas saldrán en `pending_calculation` con `total_meters`
nulo y `last_error` mencionando `ROUTE_ROUTING_URL`, o en
`Waiting for location evidence` si al viaje le falta algún waypoint. Si
apareciera cualquier otra cosa —por ejemplo `calculated` con metros y aun así
sin millas en pantalla— el diagnóstico de este reporte estaría incompleto y
habría que reabrirlo.

---

## 4. Estado de la persistencia

El disparador **existe y funciona**: `MileageService.ensure_pending` se invoca
al llegar y también cuando el viaje se interrumpe sin llegada. Verificado en la
ejecución de §2: la fila aparece en cuanto el viaje llega.

Rama de clasificación observada en la ejecución local: **Branch B — PENDING**.
No `MILEAGE RECORD NOT CREATED`: la fila se crea.

---

## 5. Evidencia de waypoint

El motor exige `start_trip`, cada `change_plan` que de verdad ocurrió, y
`arrived`. Sin ellos no enruta y lo dice —`Waiting for location evidence`— en
vez de inventar un extremo.

En la ejecución local, entregar los dos waypoints hizo avanzar el pipeline
hasta el router. Es decir: **la puerta de evidencia funciona en los dos
sentidos**, deja pasar cuando hay evidencia y se detiene cuando no.

Si en campo hay viajes atascados en este mensaje, la causa está en la captura
de ubicación del dispositivo, no en el motor. La consulta de §3 lo distingue.

---

## 6. El disparador del cálculo

| Camino de cierre | ¿Pide kilometraje? |
|---|---|
| Llegada normal (`arrive`) | **sí** |
| Llegada a casa (`arrive_home`) | **sí**, mismo camino; HOME no es un caso aparte |
| Interrupción sin llegada | **sí**, y su estado terminal propio es `not_calculable` |

No se encontró ningún camino de cierre que esquive el kilometraje.

---

## 7. Proveedor de routing en ejecución — **la causa**

Probado en ejecución, no supuesto:

```text
ROUTE_ROUTING_URL          : ''      (vacío)
ROUTE_ROUTING_FALLBACK_URL : ''      (vacío)
integración road_routing   : NO EXISTE
ADAPTADOR ACTIVO           : UnconfiguredRouter
```

`UnconfiguredRouter` falla de forma **transitoria a propósito**, y el comentario
del código explica por qué: sin motor, el kilometraje se queda
`pending_calculation` y lo terminaliza el reintento acotado, en vez de marcar
`calculation_failed` viajes cuya evidencia está intacta y cuyo único problema es
que falta desplegar un contenedor. **El primer estado se resuelve solo cuando el
motor aparece; el segundo sería una mentira sobre los datos.**

Clasificación: `ENVIRONMENT CONFIGURATION` / **DEVOPS**. No es configuración de
aplicación mal escrita: es configuración que no existe.

Hay dos caminos soportados, y el código los prefiere en este orden:

1. **Integración de plataforma `road_routing`** — la única vía para TomTom,
   porque su clave tiene que ir cifrada en la ranura de secretos. Se cambia en
   caliente desde la pantalla, sin desplegar.
2. **`ROUTE_ROUTING_URL`** (y opcionalmente `ROUTE_ROUTING_FALLBACK_URL`) — el
   camino de los motores auto-alojados tipo OSRM, que no llevan credencial.

### Un hallazgo lateral que da confianza

Durante la preparación, el motor **rechazó** mi distancia de prueba:

```text
Implausible segment 1: routed 20000m is shorter than the straight line 95627.9m,
which is geometrically impossible
```

No era un fallo: era la salvaguarda de plausibilidad certificada haciendo su
trabajo sobre un dato que yo había construido mal. Tuve que mover las
coordenadas para que el caso fuera creíble. Conviene saberlo: el motor no
acepta cualquier número que le devuelvan.

---

## 8. Reintento y barrido

| Comprobación | Resultado |
|---|---|
| El barrido existe y está registrado al arrancar | **sí** (`register_route_jobs`) |
| Encuentra los vencidos | **sí**: `examined=1` en la ejecución de §2 |
| Avanza el intento | **sí**: `attempt_count` 0 → 1 |
| Reprograma el siguiente intento | **sí**: no vuelve a tomarlo hasta que vence |
| Un reintento con éxito pasa a `calculated` | **sí**: probado en §9 con motor disponible |

### Límite de observabilidad, declarado

No puedo confirmar desde aquí que el barrido se **ejecute en el entorno
desplegado**, y §D6 avisa de que un test verde no basta para eso. Hay además un
detalle que lo hace difícil de comprobar incluso con los logs delante:

* el job corre sólo si la instancia es líder, y cuando no lo es **sale en
  silencio**, sin registrar nada;
* y el barrido sólo escribe su línea `ROUTE SWEEP` cuando encuentra algo.

Resultado: en los logs **no se distingue** «corrió y no había nada» de «nunca
corrió». No lo cambié —no es un defecto demostrado y §12 autoriza correcciones
sobre defectos demostrados— pero es una recomendación concreta en §13.

Mientras tanto, la forma de confirmarlo sin tocar código: tras configurar el
motor, ejecutar la consulta D2 de §3 dos veces separadas por el intervalo del
barrido y comprobar que `attempt_count` avanza.

---

## 9. Today / Live — traza

| | valor esperado | valor de la API | valor dibujado | clasificación |
|---|---|---|---|---|
| Fila del supervisor | `12.4` | `"12.4"` | `12.4` | **MATCH** |
| Total del día | `12.4` | `"12.4"` | `12.4` | **MATCH** |
| Marca de pendiente | sí, si está pendiente | `mileage_pending: true` | `+ pending` | **MATCH** |
| Móvil | igual que escritorio | — | `12.4` | **MATCH** |

Ningún `TODAY/LIVE PRESENTATION/WIRING DEFECT`.

---

## 10. Activity Explorer — traza

| | valor esperado | valor de la API | valor dibujado | clasificación |
|---|---|---|---|---|
| Resumen del día | `12.4` | `"12.4"` | `12.4 mi` | **MATCH** |
| Tarjeta de la parada | `12.4` | `"12.4"` | `12.4 mi` | **MATCH** |
| Agregado de semana | `12.4` | `"12.4"` | — | **MATCH** |
| Agregado de mes | `12.4` | `"12.4"` | — | **MATCH** |
| Agregado de año | `12.4` | `"12.4"` | — | **MATCH** |
| Pendiente en los tres niveles | marcado | `mileage_pending: true` | `+ pending` | **MATCH** |

Ningún `ACTIVITY UI WIRING DEFECT`. La agregación por niveles **no pierde** la
cifra, que era el riesgo específico de un explorador con tres profundidades.

**Un detalle del dominio que conviene conocer**, porque explica una lectura que
podría parecer un fallo: el explorador lista **paradas** —bloques de ejecución—
y no viajes. Un viaje que llegó y no ejecutó ninguna actividad **suma sus millas
al día** y no tiene tarjeta. No es un error: es la diferencia entre el resumen
del día y la lista de paradas.

---

## 11. Reports — estado actual

```text
REPORTS NOT YET IMPLEMENTED / NOT PART OF THIS CORRECTION
```

Evidencia: no existe módulo de API (`app/routers_api/report*` no está), no hay
página React, y el menú lo dice explícitamente —«Reports **no** está aquí: su
módulo llega en un checkpoint posterior»—. No se construyó nada de Reports, como
§3 y §9 ordenan.

---

## 12. Causa raíz

```text
observado   No se ven millas en Today / Live ni en Activity.

esperado    Un viaje con waypoints y motor disponible produce millas oficiales
            que las dos superficies enseñan igual.

causa       ROUTING PROVIDER / ADAPTER  +  ENVIRONMENT CONFIGURATION
            (`CONFIRMED` en ejecución)

            No hay motor de carretera configurado por ninguna de las dos vías
            soportadas. El adaptador activo es `UnconfiguredRouter`, que falla
            de forma transitoria por diseño, así que el kilometraje se queda
            `pending_calculation` y **nunca** llega a `calculated`.

            Causa contribuyente posible, `UNVERIFIED` en campo:
            WAYPOINT EVIDENCE GAP. Un viaje sin evidencia de ubicación se
            detiene antes, en "Waiting for location evidence". Si eso ocurre en
            campo depende de si los dispositivos reportan ubicación, y eso sólo
            se ve en la base compartida (§3).

            Descartados con evidencia:
              MILEAGE RECORD NOT CREATED      -> la fila se crea
              READ MODEL FILTER / JOIN DEFECT -> 12.4 llega entero
              BUSINESS-DAY FILTER DEFECT      -> probado con medianoche
              UNIT CONVERSION / AGGREGATION   -> 20000 m -> 12.4 mi, exacto
              TODAY/LIVE UI WIRING DEFECT     -> dibuja la cifra
              ACTIVITY UI WIRING DEFECT       -> dibuja la cifra
              REPORTS UI/READ DEFECT          -> no implementado

corrección  Ninguna. No se encontró defecto de producto que corregir, y no se
            fabrica uno para tener algo que entregar.

prueba      §2, §7, §9, §10 y las 12 pruebas nuevas de §14.
```

---

## 13. Corrección aplicada

**Ninguna al código de producto.** Es el resultado honesto del diagnóstico: la
cadena está bien y lo que falta es configuración de entorno.

Lo que sí se añadió es **la red que impide que esto se rompa en silencio**: 12
pruebas que fijan la regla de consistencia entre superficies de §10 de la
instrucción. Si algún día una unión mal escrita o un cambio de agregación
hiciera que una pantalla dijera `0.0` donde la otra dice `12.4`, ahora falla un
test en vez de descubrirse en campo.

### Acción operativa — ésta es la que arregla el síntoma

Configurar un motor de carretera, por **una** de las dos vías:

```text
A) Auto-alojado (sin credencial, se configura por entorno)
   ROUTE_ROUTING_URL = https://<osrm>/        (y opcionalmente el de reserva)

B) Comercial (TomTom), por la integración de plataforma `road_routing`
   - habilitar la integración
   - guardar la clave en la ranura de secretos, que la cifra
   - **rotar la clave anterior**: pasó por chat y hay que darla por quemada
```

Sin esto, los viajes seguirán en `pending_calculation` y las pantallas seguirán
diciendo la verdad: que todavía no se sabe.

### Recomendación, no ejecutada

Hacer observable el barrido: una línea de log cuando una instancia **no** es
líder y se salta el job, y otra cuando el barrido corre sin encontrar nada. Hoy
el silencio significa las dos cosas a la vez (§8). No lo implementé porque no es
un defecto demostrado y la instrucción autoriza correcciones sobre defectos
demostrados.

---

## 14. Consistencia entre superficies

Probado sobre **el mismo viaje y la misma lectura**, comparando carácter a
carácter:

```text
Today / Live fila   == resumen del día del explorador == tarjeta de la parada
       "12.4"       ==        "12.4"                  ==       "12.4"
```

No hay tres definiciones de kilometraje: hay una, `TripMileage.total_meters`,
y una sola conversión a millas. Los agregados difieren únicamente por el periodo
aprobado de cada superficie.

---

## 15. Pruebas y regresión

| Lote | Tests | Resultado | Exit | Tiempo |
|---|---:|---|---:|---|
| Kilometraje entre superficies (nuevo, integración) | 8 | **8 PASS** | 0 | 30 s |
| Kilometraje en pantalla (nuevo, navegador) | 4 | **4 PASS** | 0 | 58 s |
| Motor de millaje y reproceso | 29 | **28 PASS, 1 SKIP** | 0 | 51 s |
| Jornada, viajes y actividades | 145 | **145 PASS** | 0 | 165 s |
| Today / Live, Activity Explorer e integración de millas | 40 | **40 PASS** | 0 | 69 s |
| Navegador de las dos superficies | 17 | **17 PASS** | 0 | 160 s |
| `npm run check` | — | **0 errores** | 0 | — |

El `SKIP` es anterior y declarado:
`test_route_mileage_engine.py:1183 — sin ROUTE_ROUTING_URL no hay motor real que
medir (V-3)`. **Y es la misma causa que este reporte diagnostica**, vista desde
la suite: el repositorio ya decía que sin motor no se puede medir.

Cobertura de los tests pedidos:

| | Caso | Estado |
|---|---|---|
| T1 | Traza de un viaje real | **PENDING** — §3, sin datos accesibles |
| T2 | Propagación de kilometraje calculado | **PASS** (API y pantalla, las dos superficies) |
| T3 | Pendiente no es cero | **PASS** |
| T4 | Excepcional no fabrica valor | **PASS** (`not_calculable`) |
| T5 | Día de negocio | **PASS** |
| T6 | Varios viajes agregan | **PASS** |
| T7 | Varios supervisores | **PASS** |
| T8 | Aislamiento de tenant | **PASS** |
| T9 | Change Plan | **NOT APPLICABLE** — no se tocó el motor |
| T10 | Regresión | **PASS** |

---

## 16. Esperado → Implementado → Evidencia → Hueco

| Tema | Estado | Evidencia |
|---|---|---|
| Causa raíz clasificada | **VALIDATED** | §12, probado en ejecución |
| Semántica de Millas Oficiales sin cambios | **VALIDATED** | no se tocó el motor ni su definición |
| Sin respaldo de odómetro ni línea recta | **VALIDATED** | ninguna corrección aplicada |
| Pendiente ≠ cero | **VALIDATED** | §9, §10, T3 |
| Histórico no recalculado | **VALIDATED** | no se tocó ningún dato existente |
| Consistencia entre superficies | **VALIDATED** | §14 |
| Reports | **NOT IMPLEMENTED** | §11 |
| Regresión verde | **VALIDATED** | §15 |
| **Traza de un viaje real de campo** | **PENDING** | §3: 0 viajes accesibles |

**Hueco**: uno, y es de **acceso a datos**, no de implementación. La traza del
viaje real exige la base compartida.

---

## 17. Asuntos restantes

1. **Configurar el motor de carretera** (§13). Es lo que arregla el síntoma.
2. **Rotar la clave de TomTom** si se elige la vía comercial.
3. **Ejecutar las consultas de §3** contra el entorno compartido para clasificar
   los viajes de campo. Si alguno sale `calculated` con metros **y aun así** no
   se ven millas en pantalla, este diagnóstico está incompleto y hay que
   reabrirlo — lo digo explícitamente para que la predicción se pueda falsar.
4. **Observabilidad del barrido** (§13), como recomendación.
5. Deuda ya reportada y vigente: `BOOTSTRAP_COMPANY_SUBDOMAIN` sin poner, base
   abierta a internet, `exit 0` en el spec de migraciones.

---

## 18. Estado propuesto

```text
MILEAGE DATA EXCEPTION CONFIRMED — NO FABRICATED VALUE
```

Las millas no se ven porque todavía no existen, y las tres superficies —las dos
implementadas— están diciendo la verdad. No se encontró defecto de producto, no
se aplicó ninguna corrección de código, y **no se fabricó ningún valor** para
que las pantallas parecieran completas.

Lo que desbloquea el síntoma es una acción de entorno, no una decisión de
producto, así que esto **no** se propone como `BLOCKED — CER DECISION REQUIRED`.

Queda abierto el único hueco de §16 —la traza del viaje real—, que se cierra con
acceso a la base compartida.

---

## 19. Estimación del esfuerzo

| Componente | Líneas |
|---|---|
| `tests/integration/test_mileage_cross_surface.py` | 589 |
| `tests/e2e/test_mileage_cross_surface_browser.py` | 203 |
| **Total** | **792 / −0** |

| Tarea | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Diagnóstico D1–D7 y ejecución real del pipeline | `DONE` | 7 puntos | análisis | 2,2 |
| Separación de los dos bloqueos en serie | `DONE` | experimento | diagnóstico | 0,6 |
| Tests de integración entre superficies (8) | `DONE` | ~589 LoC | backend | 3,5 |
| Tests de navegador (4) | `DONE` | ~203 LoC | UI/navegador | 3,4 |
| Regresión por lotes | `DONE` | 243 tests | ejecución | 1,2 |
| Reporte 001 | `DONE` | — | documentación | 0,7 |
| **Subtotal ejecutado** | | | | **11,6** |
| Margen de riesgo (+30%, depende de un proveedor externo) | | | | **+3,5** |
| **Total** | | | | **≈ 15,1 h-agente** |

---

## 20. Siguiente paso

Configurar el motor de carretera y volver a mirar las pantallas. **No se inicia
RTE09, no se reanuda RTE10-A01 y no se rediseña Today / Live ni Activity.**
