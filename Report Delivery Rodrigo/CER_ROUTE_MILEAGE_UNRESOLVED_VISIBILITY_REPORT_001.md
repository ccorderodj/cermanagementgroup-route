# CER Route — Kilometraje sin resolver: que el cero diga por qué
## Reporte 001

**Origen:** incidente de campo observado en `cerroute.cermanagementgroup.com/admin/route/today` el 7 de octubre de 2026
**Rama:** `fix/mileage-unresolved-visibility` (desde `dev`, con el MR !62 ya fusionado)
**Fecha:** 2026-10-07
No reabre RTE06, no redefine las Millas Oficiales y no cambia ninguna cifra.

---

## 1. Resultado ejecutivo

Today / Live mostraba **siete supervisores con `0.0 mi`** y sólo uno marcado `+ pending`. El diagnóstico encontró dos cosas, y las dos están corregidas:

**Una pantalla que no podía explicar su propio cero.** La fila publicaba dos datos de kilometraje —las millas y si quedaba algo pendiente—, y con eso **tres realidades distintas se dibujaban idénticas**:

```text
no hubo ningún viaje              ->  0.0 mi
faltó evidencia de ubicación      ->  0.0 mi     `not_calculable`
el routing agotó su reintento     ->  0.0 mi     `calculation_failed`
```

Un supervisor que condujo sesenta kilómetros y perdió el GPS se veía **exactamente igual** que uno que no salió de la oficina. El cero era veraz —esos viajes no tienen kilometraje y no se les inventa uno— pero mudo, y un cero mudo obliga a abrir una consola de producción para saber qué pasó. Es lo que ocurrió.

**Un reintento que se agotaba en quince minutos.** La tolerancia a una caída del proveedor de routing era mucho menor de lo documentado. Medida contra la fórmula real, no contra el comentario:

```python
espera = backoff_base_seconds * (2 ** (intento - 1))
```

Con `max_attempts=5` son cuatro esperas —60, 120, 240 y 480 s— y después **terminal**: **15 minutos**, no los 30 que decía la documentación. Cualquier caída más larga convierte viajes buenos en pérdidas permanentes, porque **el barrido no recoge estados terminales** y conectar el proveedor después no los recupera solo.

Ahora son 10 intentos, **≈ 8,5 horas**: una jornada entera.

Lo que **no** cambió: ninguna cifra, ninguna fórmula, ningún estado del dominio. Un viaje sin resolver sigue aportando cero a las millas oficiales. Lo único que se añade es la pregunta que faltaba — *¿el cero es porque no hubo recorrido, o porque no se pudo medir?*

---

## 2. El hecho de partida

De la captura del entorno compartido:

```text
SUPERVISORS WORKING  7        TOTAL MILES TODAY  0.0
ON ROUTE             0        IN ACTIVITY        5

7 supervisores · todos 0.0 mi · sólo uno con «+ pending»
```

Esa asimetría es la que delata el problema. `+ pending` aparece **sólo** con `pending_calculation`. Y cinco de esos supervisores estaban `In Activity`, que el servidor no permite sin haber llegado:

```python
if viaje.status != TripStatus.ARRIVED.value:
    detail="Activities start once you have arrived."
```

Y al llegar se crea siempre la fila de kilometraje:

```python
# Crear la fila aquí es lo que garantiza que ningún viaje
# terminado se quede sin kilometraje que el sweeper pueda encontrar.
await MileageService.ensure_pending(...)
```

Conclusión forzosa: **esos viajes tienen registro de kilometraje y están en un estado terminal sin cifra**. La pantalla lo sabía y no lo decía.

---

## 3. Causa raíz

### 3.1 — La fila sólo tenía dos datos · `CONFIRMED`

```python
"official_miles": millas.quantize(Decimal("0.1")),
"mileage_pending": pendiente,
```

No existía ningún campo para los estados terminales. No es un defecto de cálculo ni de agregación: es **información que el dominio tenía y el contrato de lectura no transportaba**.

### 3.2 — El reintento acotado era demasiado corto · `CONFIRMED`

| `max_attempts` | Tolerancia real |
|---:|---|
| **5** (anterior) | **15 min** |
| 8 | ≈ 2,1 h |
| **10** (ahora) | **≈ 8,5 h** |
| 12 | ≈ 34 h |

El comentario del código afirmaba «unos 30 minutos». Son 15. La corrección del número y la del comentario van juntas en este delta.

---

## 4. Lo que se cambió

### Backend

| Archivo | Qué |
|---|---|
| `mileage/read.py` | **`sin_resolver()`**: expresión SQL que cuenta los terminales sin cifra. Vive junto a `metros_calculados()` y `pendientes()`, en la regla única que el MR !62 estableció |
| `live/dao.py` | Lo agrega por jornada y lo publica |
| `live/schemas.py` | `mileage_unresolved: int = 0` en el contrato |
| `core/platform/policies.py` | `max_attempts` 5 → 10, con la aritmética real documentada |

`sin_resolver()` cubre exactamente `not_calculable` y `calculation_failed`. `calculated` no está —ya tiene cifra— y `pending_calculation` tampoco, porque **«todavía no» y «ya no habrá» son preguntas distintas** y mezclarlas prometería un número que no va a llegar.

### Frontend — los cuatro sitios, no tres

El marcador `+ pending` vivía en tres componentes con su propia copia de la leyenda. Se extrajo a la entidad, junto a `formatMiles`, y se aplicó también donde faltaba:

| Componente | Antes | Ahora |
|---|---|---|
| `LiveSupervisorTable` (escritorio) | `+ pending` | `+ pending` · `· N unresolved` |
| `LiveSupervisorDetail` (panel) | `miles today · pending` | `miles today · pending · N unresolved` |
| `LiveMobileDetail` (tarjeta) | `· pending` | `· pending · N unresolved` |
| **`LiveMobileList`** (listado móvil) | **ningún motivo** | `pending · N unresolved` |

El cuarto es el hallazgo incidental y no era menor: **el listado móvil es la primera pantalla en teléfono y no mostraba ningún motivo, ni siquiera `+ pending`**. Allí el cero mudo persistía aunque todo lo demás se arreglara. Lo encontró el test de navegador en móvil, no la lectura del código.

Tres formateadores compartidos (`leyendaDeMillas`, `sufijoDeMillas`, `motivoDeMillas`) sobre una sola función privada, para que la próxima variante no nazca como una cuarta copia.

**Nada de diseño cambió**: ni disposición, ni colores, ni tamaños. Se añade texto secundario donde ya había texto secundario.

---

## 5. Validación

**253 tests · 0 fallos · 0 errores · 1 saltado · todos `exit 0`**, por lotes separados.

### Nuevos

| Archivo | Tests | Qué fija |
|---|---:|---|
| `tests/integration/test_mileage_unresolved_visibility.py` | 5 | los dos estados terminales, los tres a la vez, y los dos controles negativos |
| `tests/e2e/test_mileage_unresolved_browser.py` | 3 | escritorio, móvil, y una jornada vacía sin marcador |

Los dos estados terminales se producen por **caminos reales**, no escribiendo en la tabla:

* `not_calculable` — el cliente declara que agotó su ventana de ubicación vía `POST /api/location/missing` con `permission_denied`, que es literalmente lo que hace un teléfono sin permiso de GPS;
* `calculation_failed` — un adaptador de routing que rechaza de forma permanente, que es el camino corto al mismo estado terminal que produce agotar los intentos.

El test que más importa es el tercero: **los tres estados en una sola jornada**. Si se confundieran entre sí, la pantalla volvería a mentir — y con una mentira peor, porque ahora tendría un marcador que la respalda.

Y hay dos controles negativos, que son los que impiden un verde vacío:

* una jornada **sin viajes** debe dar `mileage_unresolved == 0`. Sin esto, un contador que devolviera siempre 1 pasaría todo lo demás;
* un viaje sin resolver **no aporta distancia**: si alguna vez sumara una estimación, sería odómetro o línea recta disfrazados de kilometraje oficial.

### Detección probada por mutación

Forcé `sin_resolver()` a devolver siempre 0:

```text
3 failed, 2 passed
  test_un_viaje_sin_evidencia_se_declara_sin_resolver
  test_un_viaje_con_routing_fallido_se_declara_sin_resolver
  test_calculado_pendiente_y_sin_resolver_son_tres_cosas_distintas
```

Revertido, 5/5 verde.

### Un defecto de mi propio montaje, corregido

El test de los tres estados fallaba porque sólo se creaban **dos** viajes. Causa: un viaje que llega y no ejecuta actividad se queda en `arrived` y no cierra, y entonces el siguiente `POST /api/trips` devuelve **ese mismo viaje** en vez de crear otro. El producto estaba bien; mi preparación estaba mal. Corregida, y el test ahora afirma explícitamente que los tres identificadores son distintos — sin esa aserción, habría vuelto a pasar comprobando dos.

### Lotes

| Lote | Tests | Fallos | Err | Skip | Exit | Seg |
|---|---:|---:|---:|---:|---:|---:|
| `test_mileage_unresolved_visibility.py` (nuevo) | 5 | 0 | 0 | 0 | 0 | 19 |
| `test_mileage_data_to_ux.py` | 6 | 0 | 0 | 0 | 0 | 34 |
| `test_mileage_cross_surface.py` | 8 | 0 | 0 | 0 | 0 | 34 |
| `test_route_mileage_engine.py` | 24 | 0 | 0 | 1 | 0 | 48 |
| `test_reprocess_failed_mileage.py` | 5 | 0 | 0 | 0 | 0 | 13 |
| `test_route_location_evidence.py` | 39 | 0 | 0 | 0 | 0 | 55 |
| `test_live_today.py` | 15 | 0 | 0 | 0 | 0 | 37 |
| `test_activity_explorer.py` | 17 | 0 | 0 | 0 | 0 | 47 |
| `test_trips.py` | 66 | 0 | 0 | 0 | 0 | 86 |
| `test_road_routing_wiring.py` | 8 | 0 | 0 | 0 | 0 | 4 |
| `test_page_wiring.py` | 33 | 0 | 0 | 0 | 0 | 6 |
| `test_navigation_wiring.py` | 9 | 0 | 0 | 0 | 0 | 6 |
| `test_frontend_source_completeness.py` | 2 | 0 | 0 | 0 | 0 | 5 |
| **navegador** `test_mileage_unresolved_browser.py` (nuevo) | 3 | 0 | 0 | 0 | 0 | 46 |
| **navegador** `test_mileage_data_to_ux_browser.py` | 3 | 0 | 0 | 0 | 0 | 64 |
| **navegador** `test_mileage_cross_surface_browser.py` | 4 | 0 | 0 | 0 | 0 | 76 |
| **navegador** `test_rte07_today_live_browser.py` | 5 | 0 | 0 | 0 | 0 | 80 |
| **navegador** `test_rte07_today_live_screenshots.py` | 1 | 0 | 0 | 0 | 0 | 22 |

El único salto es el de siempre: `sin ROUTE_ROUTING_URL no hay motor real que medir`.

* `import app.main` → **ok**
* **Frontend** `npm run check` → typecheck **0 errores**, lint **0 errores**
* **Frontend** `npm run build:prod` → **compilado**; los tests de navegador corren contra ese bundle
* **Migraciones** → `NOT APPLICABLE`

---

## 6. Lo que esto **no** resuelve

Hay que decirlo con precisión, porque es fácil confundirlo:

**Esto no recupera ninguna milla.** Hace visible un problema; no lo repara. Los viajes que ya están en `calculation_failed` siguen sin cifra hasta que alguien los reponga, y los `not_calculable` no tienen nada que recuperar: sin los dos extremos no hay distancia que pedirle a ningún proveedor, ni hoy ni nunca.

**El cambio de política no actúa sobre el pasado.** `max_attempts=10` protege a los viajes **futuros** de una caída del proveedor. Los que ya agotaron sus cinco intentos siguen terminales.

---

## 7. Acción operativa

**1 · Clasificar** lo que hay hoy en el entorno compartido — sólo lectura:

```bash
python -m app.db.scripts.trace_trip_mileage --company cerroute --recent 50
```

**2 · Reponer lo recuperable**, si aparecen `calculation_failed`. Simula por omisión:

```bash
python -m app.db.scripts.reprocess_failed_mileage --company cerroute \
    --desde 2026-10-01 --hasta 2026-10-07
```

y de nuevo con `--aplicar` cuando la lista cuadre. Comprobar antes que el chequeo `road_routing` de `/admin/platform/diagnostics` esté en `healthy`.

**3 · Desplegar este cambio.** Es frontend además de backend, así que necesita el bundle reconstruido — el job ya hace `build:prod`. Sin migración y sin comandos de consola.

**4 · Si predominan los `not_calculable`:** la acción no es de software. Es permiso de ubicación en los teléfonos de los supervisores. Ninguna corrección de código puede sustituir un punto GPS que nunca se capturó.

**Nota sobre el valor nuevo:** `max_attempts` es política de plataforma, así que si el entorno compartido tiene una fila de anulación con el valor 5, el nuevo valor por omisión **no** lo cambia. Comprobarlo en la pantalla de plataforma tras desplegar.

---

## 8. Asuntos restantes

**Dentro de este alcance: ninguno.**

**Decisión pendiente de CER, no mía:** que un `calculation_failed` por agotamiento del proveedor se reabra solo cuando el motor vuelva a estar sano. Resolvería el caso de raíz, pero **un estado terminal que se reabre solo deja de ser terminal**, y esa semántica está certificada en RTE06. Con la tolerancia ahora en 8,5 horas probablemente no haga falta; si el caso reaparece, ésta es la conversación.

**Observación de alcance:** este delta toca Today / Live. El Activity Explorer publica `mileage_pending` en su resumen y tampoco distingue los terminales. No lo incluí porque el incidente fue en Today / Live y porque ampliar sin pedirlo convertiría una corrección en un rediseño — pero **la asimetría queda abierta** y la señalo aquí para que sea una decisión y no un olvido. Serían ≈ 3 h-agente.

---

## 9. Estado propuesto

```text
MILEAGE UNRESOLVED VISIBILITY COMPLETE / READY FOR CER REVIEW
```

No se declara nada cerrado: la certificación es de CER.

---

## 10. Estimación del esfuerzo

| Componente | Líneas |
|---|---:|
| `tests/integration/test_mileage_unresolved_visibility.py` | 272 |
| `tests/e2e/test_mileage_unresolved_browser.py` | 141 |
| Modificados (10 archivos) | +165 / −12 |
| **Total** | **≈ 578 / −12** |

| Tarea | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Diagnóstico del incidente a partir de la captura | `DONE` | — | análisis | 0,8 |
| Medición de la aritmética real del reintento | `DONE` | — | diagnóstico | 0,3 |
| `sin_resolver()` y agregado en Today / Live | `DONE` | ~40 LoC | backend | 0,6 |
| Frontend: formateadores compartidos y cuatro componentes | `DONE` | ~70 LoC | UI | 1,4 |
| Ajuste y documentación de la política | `DONE` | ~26 LoC | backend | 0,3 |
| Tests de integración (5), mutación incluida | `DONE` | ~272 LoC | integración | 2,8 |
| Tests de navegador (3) y el hallazgo del listado móvil | `DONE` | ~141 LoC | UI/navegador | 2,4 |
| Regresión por lotes (253 tests) + dos builds | `DONE` | 18 lotes | ejecución | 1,2 |
| Reporte | `DONE` | — | documentación | 0,6 |
| **Subtotal ejecutado** | | | | **10,4** |
| Margen de riesgo (+50%, automatización de navegador) | | | | **+5,2** |
| **Total del delta** | | | | **≈ 15,6 h-agente** |

---

## 11. Siguiente paso

Desplegar, y después ejecutar los pasos 1 y 2 de §7 para clasificar y reponer lo que haya quedado atrás. **No se inicia Reports, ni RTE09, ni se reanuda RTE10-A01.**
