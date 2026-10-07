# CER Route — Kilometraje: del dato persistido a la pantalla
## Reporte 003

**Instrucción:** `CER_ROUTE_MILEAGE_DATA_TO_UX_CLOSURE_INSTRUCTIONS_003.md`
**Rama:** `fix/mileage-data-to-ux-closure` (desde `dev`)
**Fecha:** 2026-10-07
No reabre RTE06 y no redefine las Millas Oficiales.

---

## 1. Resultado ejecutivo

**Se encontraron dos defectos reales, los dos en el camino `dato → pantalla`, y los dos están corregidos.** Ninguno estaba en el motor de kilometraje ni en el proveedor de routing: el dato persistido siempre fue correcto.

**Defecto 1 — dos fórmulas de conversión.** El repositorio convertía metros a millas de dos maneras distintas:

```text
exacta       metros / 1609.344        <- API de kilometraje, 2 decimales
aproximada   metros * 0.000621371     <- Today / Live y Activity, 1 decimal
```

`1/1609.344 = 0.000621371192237…`, así que la segunda es la primera truncada. Suena a ruido y no lo es: **a 57 695 m —57,7 km, una jornada corriente— la exacta publica 35,9 millas y la truncada 35,8.** El mismo viaje, dos cifras, según la pantalla por la que se mire. Es literalmente la «segunda fórmula de reporte» que §3 prohíbe.

**Defecto 2 — el Activity Explorer abría en el día del navegador.** La pantalla inicializaba su fecha con `new Date()` del dispositivo en vez de preguntar al servidor cuál es el día de negocio vigente. Cuando los dos no coinciden —desfase horario, o sencillamente que uno ya cruzó la medianoche y el otro no— el explorador abre en el día equivocado y muestra `No recorded activity on this day` **sobre una jornada que sí tuvo actividad**. §12 lo prohíbe de forma expresa.

Ése segundo es, con alta probabilidad, el que CER observó como *«kilometraje que existe en datos y no se ve de forma fiable»*: no falla siempre, falla según la hora y el dispositivo. Lo reproduje y lo capturé antes de tocarlo (§5).

Lo que **no** se encontró, habiéndolo buscado: ninguna duplicación por joins, ninguna fórmula en el cliente, ningún uso de odómetro o línea recta, y ninguna divergencia entre las dos superficies en qué día es hoy.

Y una cosa más que §7 pedía y no existía: **ahora hay una sola regla autoritativa de lectura**, en `app/routers_api/mileage/read.py`, que alimenta Today / Live, Activity Explorer y el futuro Reports.

---

## 2. El dato de partida

```text
company_id         : 1
supervisor user_id : 8
work_session_id    : 1
session_date       : 2026-10-07
trip_id            : 1
trip_mileage_id    : 1
state              : calculated
total_meters       : 57695.00
tramos / proveedor : 1 / fijo/test
calculated_at      : 2026-10-07 01:16:17 UTC
Official Miles     : 35.9
```

**MV-01 PASS**: existe un kilometraje `calculated` con `total_meters` positivo, persistido.

Nota de alcance honesta: el proveedor de routing de este registro es el doble de pruebas, no TomTom. Lo que esta entrega cierra es el tramo **`dato persistido → modelo de lectura → API → UX`**, y ese tramo empieza *después* del proveedor: para él, 57 695 m persistidos por TomTom y 57 695 m persistidos por el doble son el mismo dato de entrada. El tramo del proveedor es el del cierre de campo anterior y CER ya confirmó que funciona (§1 de la instrucción).

---

## 3. Evaluación del SELECT de extracción

§4 pedía usar la extracción previa como **referencia diagnóstica** y no convertirla en el contrato de la API. Así se hizo: sirvió para entender las relaciones, y el contrato de producción siguió siendo el de las dos superficies.

La advertencia de §4 sobre duplicación es correcta en general y **no se materializa aquí**. Verificado contra la base, no contra comentarios:

| Ruta de lectura | Uniones | ¿Puede duplicar? |
|---|---|---|
| Today / Live | `Trip ⋈ TripMileage` | **No**: `uq_trip_mileage_trip` hace la relación 1:1 |
| Activity, agregado del día | `WorkSession ⋈ Trip ⟕ ActivityExecution ⟕ TripMileage` | **No**: `uq_activity_execution_trip` hace 1:1 también el bloque de actividad |
| Activity, tarjetas de parada | una fila por bloque, **sin** `SUM` | **No**: no agrega |
| Cualquiera | — | **Ninguna** une `trip_mileage_segment` |

Las dos propiedades que sostienen la corrección son **restricciones de la base**, no convenciones:

```sql
UniqueConstraint("trip_id", "company_id", name="uq_trip_mileage_trip")
UniqueConstraint("trip_id",               name="uq_activity_execution_trip")
```

El docstring del agregado afirmaba «un viaje tiene un bloque de actividad como máximo»; eso era una afirmación hasta que se comprobó cuál es la restricción que la garantiza. Ahora está comprobada y hay tests que la defienden (§9).

---

## 4. Fuente autoritativa del kilometraje

Sigue siendo la del dominio: `TripMileage.total_meters` de los viajes en estado `calculated`. No se introdujo ninguna tabla nueva, ninguna vista y ninguna persistencia para conveniencia de la interfaz.

Lo que sí se introdujo es **el punto único donde esa fuente se interpreta**: `app/routers_api/mileage/read.py`, 105 líneas, sin estado y sin acceso a base.

```python
METROS_POR_MILLA = Decimal("1609.344")   # exacto por definición

def millas_oficiales(metros, *, precision=UNA_DECIMA) -> Decimal
def metros_calculados()   # expresión SQL: sólo `calculated` suma
def pendientes()          # expresión SQL: 1 por cada `pending_calculation`
```

Se **divide** por 1609,344 en lugar de multiplicar por su inverso, y eso es la corrección: el inverso no tiene representación decimal finita, así que cualquier constante multiplicativa es necesariamente una truncada.

Antes de este delta la regla estaba repartida así:

| Pieza | Copias antes | Después |
|---|---:|---:|
| Constante de conversión | **4** (`live/dao`, `activityexplorer/dao`, `activityexplorer/router`, el trazador) + la exacta en `mileage/service` | **1** |
| «Qué millaje suma» (`calculated`) | 2 | 1 |
| «Qué queda pendiente» | 2 | 1 |

`miles_from_meters` conserva su firma pública y sus dos decimales —es la respuesta sobre **un viaje**, donde `None` y cero no son lo mismo— pero ahora delega en la regla compartida.

---

## 5. Causa raíz encontrada

### Defecto 1 — `Case A`: el modelo de lectura usaba una segunda fórmula

```text
DATABASE VALUE    57695.00 m
READ MODEL        57695.00 m        correcto
API VALUE         35.8 mi           <- aqui se pierde, por la formula truncada
RENDERED VALUE    35.8 mi
```

Medición de la divergencia, no estimación:

```text
error relativo del multiplicador : 3,09e-7
primera discrepancia a 1 decimal : 57 695 m  -> exacta 35.9  aproximada 35.8
primera discrepancia a 2 decimales:  8 956 m  -> exacta  5.57 aproximada  5.56
```

A dos decimales la divergencia empieza en **8,9 km**, que es un solo trayecto corto. La API de kilometraje publica dos decimales, así que la contradicción entre pantallas era alcanzable casi a diario.

### Defecto 2 — `Case B`: la UI pedía el día equivocado

```text
DATABASE VALUE    57695.00 m, session_date 2026-10-07
READ MODEL        correcto
API VALUE         correcto, para el dia que se le pida
RENDERED VALUE    0.0 mi  +  "No recorded activity on this day"
```

Capturado antes de corregir, sobre la base con el viaje ya calculado:

```text
ESTADO: ('calculated', Decimal('57695.00'))
DIA JORNADA: 2026-10-07
=== MOVIL ACTIVITY ===
  Activity
  Day | Week | Month | Year
  0.0 mi  miles   0m activity time   0 activities
  No recorded activity on this day.
```

El código responsable:

```tsx
function hoyLocal(): string {
    const d = new Date();          // ← el calendario del DISPOSITIVO
    ...
}
const [fecha, setFecha] = useState<string>(hoyLocal);
```

Y la petición mandaba siempre ese valor, de modo que el servidor **nunca llegaba a aplicar** su propia regla de día de negocio, que ya existía y era correcta.

Lo irónico es que el patrón correcto estaba tres líneas más abajo, aplicado al supervisor:

```tsx
// El servidor decide qué supervisor queda seleccionado cuando la
// pantalla todavía no lo sabe. El alcance es suyo, no de aquí.
```

Faltaba decir lo mismo del día.

**Comprobado que el defecto era exclusivo del Explorer**: `Today / Live` no calcula ninguna fecha en el cliente, y una búsqueda de `new Date()` en las superficies de Route no devuelve nada más.

---

## 6. Corrección del modelo de lectura

Ninguna semántica cambió. Lo que cambió es quién decide.

| Archivo | Qué |
|---|---|
| `app/routers_api/mileage/read.py` | **nuevo**, 105 líneas: la regla única |
| `app/routers_api/mileage/service.py` | `miles_from_meters` delega; `METROS_POR_MILLA` se reexporta por compatibilidad |
| `app/routers_api/live/dao.py` | −44/+13: usa las expresiones y la conversión compartidas |
| `app/routers_api/activityexplorer/dao.py` | −40/+13: idem; desaparecen sus dos expresiones locales |
| `app/routers_api/activityexplorer/router.py` | −7/+2: la cuarta copia de la constante |
| `app/db/scripts/trace_trip_mileage.py` | −8/+4: la quinta |
| `.../explorerService.ts` | `date` pasa a `string \| null`; si es nulo **no se envía** |
| `.../RouteActivityExplorerPage.tsx` | `hoyLocal()` eliminado; el día inicial llega del servidor |

La corrección del frontend es de **mapeo únicamente**, como §6 Caso B autoriza. No se tocó ni un estilo, ni un texto, ni la disposición. V0.7 intacto.

Sobre el resumen de Today / Live: suma las millas **ya convertidas** de cada supervisor, en lugar de convertir la suma de metros. Se conservó a propósito — así el total siempre cuadra con las filas que el usuario tiene delante, que es la propiedad que una pantalla de resumen no puede romper. La diferencia frente a convertir el total es de ±0,05 millas por supervisor y está declarada aquí para que no se descubra como sorpresa.

---

## 7. Traza de Today / Live

```text
TripMileage.total_meters   57695.00
  -> metros_calculados()   57695.00   (solo `calculated`)
  -> millas_oficiales()    35.9
  -> /api/live/today       supervisors[user_id=8].official_miles = 35.9
  -> summary.total_miles   35.9
  -> mileage_pending       False
  -> escritorio            35.9 mi    (navegador real)
  -> movil 390x844         35.9 mi    (navegador real)
```

**MV-02 PASS · MV-03 PASS.**

El test de navegador comprueba además que **`35.8 mi` no aparece en ninguna parte de la página**. Sin ese control, un verde no distinguiría «dibuja bien» de «no dibuja nada».

---

## 8. Traza de Activity Explorer

```text
TripMileage.total_meters   57695.00
  -> agregado del dia      57695.00
  -> summary.official_miles        35.9
  -> activities[0].official_miles  35.9   (la tarjeta de la parada)
  -> range/start                   day 2026-10-07
  -> escritorio                    35.9 mi
  -> movil 390x844                 35.9 mi
```

**MV-04 PASS · MV-05 PASS.**

Los tests de navegador abren la pantalla **sin decirle la fecha**, que es la verificación del defecto 2: antes mostraban `0.0 mi`; ahora abren solas en el día correcto.

En móvil la línea base V0.7 oculta los campos del filtro, así que allí sólo es alcanzable el día vigente. Eso se respeta —no se rediseñó nada— y por eso la comprobación móvil es exactamente la que el usuario puede hacer: abrir y mirar.

---

## 9. Validación de duplicación y agregación

| Escenario | Montaje | Resultado |
|---|---|---|
| **MV-06** Dos viajes calculados en una jornada | 2 × 20 000 m | suman una vez cada uno |
| **MV-07a** Una parada con **tres** actividades elegidas | `activity_execution_activity` 1:N | **35.9**, una sola vez, y **una** tarjeta |
| **MV-07b** Viaje con cambio de plan → **dos tramos** | 2 segmentos, `total_meters` = 115 390 | el día lo cuenta **una** vez: 71.7 mi |
| **MV-08** Calculado + pendiente el mismo día | 1 con evidencia, 1 sin | 35.9 visibles **y** `mileage_pending = true` |

MV-07a es el que importa: `activity_execution` está protegida por una restricción única, pero **`activity_execution_activity` es uno-a-muchos y no la protege nada**. Si alguna consulta la uniera, un viaje con tres actividades aportaría sus millas tres veces. El test lo monta y lo descarta.

MV-07b fija la otra mitad: los tramos son procedencia de auditoría, no millas adicionales. `total_meters` ya es el total del viaje y no se le suman sus segmentos.

**MV-06 PASS · MV-07 PASS · MV-08 PASS.**

---

## 10. Comportamiento de lo pendiente

Semántica conservada, sin tocarla.

* Un viaje sin resolver **no** aporta cero a la suma: queda fuera de `metros_calculados()` y se anuncia por separado con `pendientes()`.
* `mileage_pending` llega a las dos superficies y la UI lo dibuja como `+ pending`.
* `pendientes()` cuenta **sólo** `pending_calculation`. Un estado terminal —`not_calculable`, `calculation_failed`— ya no está pendiente de nada, y presentarlo como «todavía calculando» sería prometer una cifra que no va a llegar.

Esa distinción estaba implícita en las dos copias y ahora está escrita una vez, con su motivo.

---

## 11. Aislamiento de tenant y supervisor

**MV-10 PASS**, sin cambios: todo el alcance sigue saliendo del subdominio y del `user_id` de la jornada, nunca de la petición.

* `test_las_millas_de_un_tenant_no_pasan_al_otro`
* `test_las_millas_de_un_supervisor_no_pasan_a_otro`
* `test_no_se_ven_supervisores_de_otro_tenant`
* Un supervisor de otra compañía pedido por identificador devuelve **404**, no 403.

No se tocaron roles ni capacidades (§13, §17).

**MV-09 PASS**: `test_el_kilometraje_se_queda_en_su_dia_de_negocio` sigue verde — las millas no aparecen en el día natural siguiente. Y el defecto 2 era precisamente una erosión de esta regla **en el cliente**; corregirlo la refuerza.

---

## 12. Tests y regresión

**332 tests · 0 fallos · 0 errores · 1 saltado · todos `exit 0`**, por lotes separados.

### Nuevos

| Archivo | Tests | Qué fija |
|---|---:|---|
| `tests/integration/test_mileage_data_to_ux.py` | 6 | la conversión única, MV-02/04/07/08, y la lista cerrada |
| `tests/e2e/test_mileage_data_to_ux_browser.py` | 3 | MV-03 y MV-05 en navegador real, escritorio y móvil |

### Que los tests **detectan** el defecto, probado por mutación

Reintroduje el multiplicador truncado en `millas_oficiales` y volví a correr:

```text
4 failed, 2 passed
  test_la_conversion_es_la_division_exacta
  test_las_dos_superficies_publican_la_cifra_exacta
  test_varias_actividades_en_una_parada_no_multiplican_las_millas
  test_calculado_y_pendiente_en_el_mismo_dia
```

Revertido, 6/6 verde. **Antes de este delta las dos pantallas usaban exactamente esa fórmula y ningún test fallaba**, porque todos medían con 20 000 m — 12,4 por las dos vías. Un verde que no distinguía nada.

Hay además una comprobación de lista cerrada, con el mismo recurso que `test_public_surface.py` usa para la superficie pública: si `0.000621371` reaparece en `app/`, el test falla y nombra el archivo.

### Lotes

| Lote | Tests | Fallos | Err | Skip | Exit | Seg |
|---|---:|---:|---:|---:|---:|---:|
| `test_mileage_data_to_ux.py` (nuevo) | 6 | 0 | 0 | 0 | 0 | 17 |
| `test_mileage_cross_surface.py` | 8 | 0 | 0 | 0 | 0 | 24 |
| `test_route_mileage_engine.py` | 24 | 0 | 0 | 1 | 0 | 30 |
| `test_reprocess_failed_mileage.py` | 5 | 0 | 0 | 0 | 0 | 9 |
| `test_trace_trip_mileage.py` | 6 | 0 | 0 | 0 | 0 | 16 |
| `test_route_location_evidence.py` | 39 | 0 | 0 | 0 | 0 | 36 |
| `test_trips.py` | 66 | 0 | 0 | 0 | 0 | 55 |
| `test_live_today.py` | 15 | 0 | 0 | 0 | 0 | 24 |
| `test_activity_explorer.py` | 17 | 0 | 0 | 0 | 0 | 35 |
| `test_activities.py` | 37 | 0 | 0 | 0 | 0 | 41 |
| `test_road_routing_wiring.py` | 8 | 0 | 0 | 0 | 0 | 2 |
| `test_tomtom_router.py` | 13 | 0 | 0 | 0 | 0 | 2 |
| `test_permission_catalog.py` | 7 | 0 | 0 | 0 | 0 | 3 |
| `test_public_surface.py` | 14 | 0 | 0 | 0 | 0 | 4 |
| `test_page_wiring.py` | 33 | 0 | 0 | 0 | 0 | 4 |
| `test_navigation_wiring.py` | 9 | 0 | 0 | 0 | 0 | 4 |
| `test_frontend_source_completeness.py` | 2 | 0 | 0 | 0 | 0 | 3 |
| **navegador** `test_mileage_data_to_ux_browser.py` (nuevo) | 3 | 0 | 0 | 0 | 0 | 40 |
| **navegador** `test_mileage_cross_surface_browser.py` | 4 | 0 | 0 | 0 | 0 | 46 |
| **navegador** `test_rte08_activity_explorer_browser.py` | 8 | 0 | 0 | 0 | 0 | 78 |
| **navegador** `test_rte08_activity_explorer_screenshots.py` | 1 | 0 | 0 | 0 | 0 | 22 |
| **navegador** `test_rte08_activity_access_browser.py` | 2 | 0 | 0 | 0 | 0 | 26 |
| **navegador** `test_rte07_today_live_browser.py` | 5 | 0 | 0 | 0 | 0 | 52 |

El único salto es el de siempre: `sin ROUTE_ROUTING_URL no hay motor real que medir`.

* `import app.main` → **ok**
* **Frontend** `npm run check` → typecheck **0 errores**, lint **0 errores**
* **Frontend** `npm run build:prod` → **compilado**, y los tests de navegador corren contra ese bundle
* **Migraciones** → `NOT APPLICABLE`: ningún cambio de esquema

---

## 13. Esperado → Implementado → Evidencia → Hueco

| MV | Escenario | Estado | Evidencia |
|---|---|---|---|
| MV-01 | Un viaje calculado persistido | **PASS** | §2, `trip_mileage_id=1`, 57 695,00 m |
| MV-02 | Base → API de Today / Live | **PASS** | §7 |
| MV-03 | Today / Live → UX, escritorio y móvil | **PASS** | §7, navegador real |
| MV-04 | Base → API de Activity | **PASS** | §8 |
| MV-05 | Activity → UX | **PASS** | §8, navegador real |
| MV-06 | Varios viajes agregan una vez cada uno | **PASS** | §9 |
| MV-07 | Las uniones no duplican | **PASS** | §9, dos vectores probados |
| MV-08 | Calculado + pendiente | **PASS** | §9, §10 |
| MV-09 | Jornada que cruza medianoche | **PASS** | §11 |
| MV-10 | Aislamiento tenant / supervisor | **PASS** | §11 |

| # | Criterio de §18 | Estado |
|---:|---|---|
| 1 | Viaje calculado persistido demostrado | **VALIDATED** |
| 2 | `total_meters` y Millas Oficiales conocidos | **VALIDATED** |
| 3 | API de Today / Live correcta | **VALIDATED** |
| 4 | Today / Live lo muestra | **VALIDATED** |
| 5 | API de Activity correcta | **VALIDATED** |
| 6 | Activity lo muestra y lo agrega | **VALIDATED** |
| 7 | Varios viajes, una vez cada uno | **VALIDATED** |
| 8 | Las uniones no pueden duplicar | **VALIDATED** |
| 9 | Lo pendiente sigue siendo veraz | **VALIDATED** |
| 10 | Semántica del día de negocio | **VALIDATED** — y **reforzada**: §5, defecto 2 |
| 11 | Aislamiento correcto | **VALIDATED** |
| 12 | No se introdujo una fórmula nueva | **VALIDATED** — se **eliminó** una |
| 13 | Sin odómetro ni Haversine de reserva | **VALIDATED** |
| 14 | Regresión afectada verde | **VALIDATED** — §12 |
| 15 | Sin hueco inexplicado en base → API → UX | **VALIDATED** |

**Hueco dentro de este alcance: ninguno.**

---

## 14. El contrato que reutiliza Reports

Reports **no** se construyó (§10). Lo que queda listo es de dónde tendrá que leer:

```python
from app.routers_api.mileage.read import (
    millas_oficiales,   # metros -> millas, con la precisión que la pantalla pida
    metros_calculados,  # expresión SQL: sólo `calculated` suma
    pendientes,         # expresión SQL: lo que sigue sin resolverse
)
```

Sirve para las cuatro granularidades que §7 enumera —por viaje, por jornada o día de negocio, por supervisor y periodo, y si queda algo pendiente— porque las dos expresiones se agrupan por lo que cada consumidor necesite.

```text
                 TripMileage (calculated)
                           │
              mileage/read.py  (regla única)
                           │
        ┌──────────────────┼──────────────────┐
   Today / Live      Activity Explorer      Reports
```

La condición es una: **Reports no debe traer su propia conversión**. Si aparece una tercera, vuelve exactamente el defecto que este delta cierra — y el test de lista cerrada de §12 lo detendrá en CI.

---

## 15. Asuntos restantes

**Dentro de este alcance: ninguno.**

**Acción operativa:** desplegar. La corrección del Explorer es de frontend, así que **exige el bundle reconstruido** — el job de despliegue ya hace `npm run build:prod`, de modo que basta con que el commit llegue a `dev`. No hay migración y no hay comando que ejecutar en consola.

**Observación, no bloqueante:** el registro de este reporte se calculó con el doble de routing, no con TomTom. El tramo que cierra esta entrega empieza después del proveedor y es indiferente a quién produjo los metros; aun así, **recomiendo que CER repita la traza de §2 con un viaje real de TomTom en el entorno compartido** usando `trace_trip_mileage --trip <ID>` y compruebe que la cifra que imprime coincide con la de las dos pantallas. Son dos minutos y convierten esto en evidencia de campo.

**Fuera de alcance, ya reportado antes:** el selector de supervisor aparece vacío mientras no haya perfiles de supervisor dados de alta; y la fragilidad del arnés de tests al mezclar módulos en una sola invocación.

---

## 16. Estado propuesto

```text
ROUTE MILEAGE DATA-TO-UX CLOSURE COMPLETE / READY FOR CER CERTIFICATION
```

Dos defectos reales encontrados y corregidos, los diez escenarios obligatorios en verde, la duplicación por uniones descartada con restricciones de base y con tests, una sola regla de lectura para las tres superficies, y la detección probada por mutación.

**No se declara `ROUTE MILEAGE CLOSED`:** la certificación es de CER.

---

## 17. Estimación del esfuerzo

| Componente | Líneas |
|---|---:|
| `app/routers_api/mileage/read.py` | 105 |
| `tests/integration/test_mileage_data_to_ux.py` | 421 |
| `tests/e2e/test_mileage_data_to_ux_browser.py` | 163 |
| Modificados (8 archivos) | +70 / −90 |
| **Total** | **≈ 759 / −90** |

| Tarea | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Auditoría de las dos rutas de lectura y de las uniones | `DONE` | ~700 LoC leídas | análisis | 1,0 |
| Hallazgo y **medición** de la divergencia de fórmulas | `DONE` | — | diagnóstico | 0,7 |
| Regla de lectura compartida | `DONE` | ~105 LoC | backend | 0,7 |
| Migrar las cinco copias a la regla única | `DONE` | 6 archivos | backend | 1,2 |
| Hallazgo del día del navegador y corrección | `DONE` | ~39 LoC front | UI | 1,3 |
| Tests de integración (6), mutación incluida | `DONE` | ~421 LoC | integración | 4,2 |
| Tests de navegador (3), escritorio y móvil | `DONE` | ~163 LoC | UI/navegador | 2,6 |
| Captura de la traza principal | `DONE` | — | evidencia | 0,4 |
| Regresión por lotes (332 tests) + build | `DONE` | 23 lotes | ejecución | 1,4 |
| Reporte 003 | `DONE` | — | documentación | 0,8 |
| **Subtotal ejecutado** | | | | **14,3** |
| Margen de riesgo (+50%, automatización de navegador) | | | | **+7,2** |
| **Total del delta** | | | | **≈ 21,5 h-agente** |

---

## 18. Siguiente paso

Desplegar `dev` y repetir la traza de §2 con un viaje real de TomTom en el entorno compartido.

**No se inicia Reports. No se inicia RTE09. No se reanuda RTE10-A01.** A la espera de la revisión de CER.
