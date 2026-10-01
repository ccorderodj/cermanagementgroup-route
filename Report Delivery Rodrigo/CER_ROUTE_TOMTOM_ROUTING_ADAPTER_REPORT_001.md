# CER Route — Adaptador de routing TomTom y reproceso de kilometraje — Reporte 001

**Fecha**: 2026-10-01
**Alcance**: tercer adaptador de routing (TomTom) y comando de reposición de kilometrajes fallidos
**Estado**: `COMPLETED` para el adaptador; `COMPLETED WITH PENDING ITEMS` para la integración de plataforma
**Rama**: `feature/tomtom-routing-adapter`

---

## 1. Status

`COMPLETED WITH PENDING VALIDATION`. El código está terminado y probado contra
dobles; **no se ha ejecutado contra la API real de TomTom** porque no hay clave,
y eso es exactamente lo que un doble no puede demostrar.

Hay además una **comprobación contractual pendiente que no es técnica** y que
puede invalidar la decisión entera. Está en §4.1 y conviene leerla antes que
nada.

---

## 2. Por qué se hizo, y qué había antes

El entorno de pruebas devolvía en todos los viajes
`calculation_failed / routing_exhausted`, con el mensaje
`No road routing engine is configured (ROUTE_ROUTING_URL is empty)`. No hay
motor desplegado.

El módulo nacía con la decisión de proveedor **cerrada**: OSRM auto-alojado de
primario, Valhalla de reserva, los dos sobre datos OSM. Se recomendó ese camino
—OSRM con extracto de Georgia en DigitalOcean— y CER decidió evaluar TomTom.
El propio módulo ya preveía esto: *"Un proveedor comercial se enchufa aquí el día
que CER lo decida, escribiendo un adaptador. El motor de kilometraje no cambia."*

---

## 3. Qué se entrega

| Archivo | Qué es |
|---|---|
| `app/routers_api/mileage/routing.py` | `TomTomRouter`, y `get_road_router()` reescrito para montarlo |
| `app/core/platform/providers.py` | Integración `road_routing` con tres proveedores |
| `app/db/scripts/reprocess_failed_mileage.py` | El comando de reposición |
| `tests/test_tomtom_router.py` | 13 tests del adaptador |
| `tests/integration/test_reprocess_failed_mileage.py` | 5 tests de la reposición |

### 3.1 Tres decisiones del adaptador que conviene conocer

**La clave va cifrada, no en una variable de entorno.** `ROUTE_ROUTING_URL` es
texto plano **a propósito**, porque el diseño asume motores auto-alojados sin
credencial. Meter ahí una clave de API la dejaría en claro, que es de lo que
AGENTS.md prohíbe expresamente. La clave de TomTom entra por la ranura de
secretos de plataforma —AES-256-GCM con la llave maestra fuera de la base—,
igual que el secreto de Microsoft 365 o la del escáner.

Eso obligó a declarar la integración `road_routing`, con los tres proveedores:
OSRM y Valhalla (sólo URL) y TomTom (clave + endpoint).

**`traffic=false`, y no es un detalle de rendimiento.** TomTom calcula por
defecto con el tráfico del momento, así que **los mismos dos puntos devuelven
distancias distintas según cuándo se pregunte**. Para un hecho que §27 y §28
obligan a conservar y auditar para siempre, eso rompe la reproducibilidad: quien
recalcule un viaje de hace un mes no obtendría el mismo número. Con el tráfico
desactivado la respuesta depende sólo del grafo. Se pierde el desvío por atasco,
y es un intercambio deliberado: aquí interesa la distancia, no el tiempo.

**La clave no puede salir en un mensaje de error.** Va como parámetro en la URL,
que es como TomTom la acepta, y las excepciones de `httpx` suelen incluir la URL.
El mensaje de este adaptador acaba en `trip_mileage.last_error`, que **se
conserva** y se lee en diagnósticos: sin redactar, la clave quedaría escrita en
la base para siempre y visible para cualquiera que consulte por qué falló un
tramo. Todo texto que viene de fuera pasa por `_redactar`, y hay un test que lo
comprueba.

### 3.2 El orden de coordenadas

TomTom usa `lat,lon`; OSRM usa `lon,lat`. Invertirlo **devuelve distancias
plausibles de otro sitio**: no rompe nada y miente, que es el peor modo de fallo
posible. Es también el error más probable, porque un copiar-pegar entre los dos
adaptadores lo produce. `test_orden_lat_lon` fija la URL completa con
coordenadas conocidas.

### 3.3 El comando de reposición

`sweep_pending_mileage` sólo recoge `pending_calculation`. Un
`calculation_failed` es **terminal y no se reintenta nunca**, así que desplegar
un motor **no recupera** lo que falló mientras no lo había.

Reabrir hechos terminalizados es una decisión de negocio, no una corrección
técnica, y por eso es un comando explícito con rango de fechas y **simulación
por defecto**, no un trabajo de fondo.

Repone sólo las razones que describen al motor —`routing_exhausted` e
`implausible_segment`—. **No** toca `start_waypoint_missing`,
`arrival_waypoint_missing`, `change_plan_waypoint_missing`,
`interrupted_without_arrival` ni los `not_calculable`: a esos les falta un
waypoint y ningún motor nuevo los arregla; reponerlos gastaría intentos para
volver al mismo sitio.

Cada fila repuesta deja su `audit_event` con acción `requeued`. Un cambio de
estado hecho a mano que no se audita es indistinguible de uno que no ocurrió.

```bash
# Simulación, que es el modo por defecto.
uv run python -m app.db.scripts.reprocess_failed_mileage --company 1

# Aplicando, acotado por fecha de jornada.
uv run python -m app.db.scripts.reprocess_failed_mileage \
    --company 1 --desde 2026-09-01 --hasta 2026-09-30 --aplicar
```

---

## 4. Hallazgos

### 4.1 El que puede invalidar la decisión — `UNVERIFIED`

El docstring del módulo explica por qué los dos motores originales son
auto-alojados, y **la razón no es el precio**:

> *"§27 y §28 obligan a guardar la distancia de cada tramo para siempre y a que
> siga siendo auditable, y los términos de servicio de Google Routes y Mapbox
> Directions restringen justamente el almacenamiento permanente de contenido
> derivado de su routing. Eso es un conflicto directo con un criterio de
> aceptación, no un detalle de coste."*

**No he leído los términos de TomTom y no sé si permiten conservar
indefinidamente la distancia derivada.** Es una verificación contractual que le
corresponde a CER, y si la respuesta es que no, el adaptador no se puede usar con
datos reales por mucho que funcione.

Está escrito como aviso en la ficha del proveedor, para que quien lo configure lo
lea antes de guardar la clave. **Es revisión humana, no un fallo de ingeniería.**

### 4.2 De diseño, `CONFIRMED`

**Un 403 de TomTom se clasifica como permanente.** TomTom usa 403 tanto para
clave inválida como para cuota agotada. Una cuota diaria no se rearma dentro de
los cinco intentos del backoff —unos 30 minutos—, así que tratarlo como
transitorio gastaría los intentos para acabar en el mismo sitio media hora
después. Un `calculation_failed` con el mensaje de credencial dice lo que hay que
arreglar. El 429, en cambio, sí es transitorio: el límite por segundo se rearma
solo.

**El adaptador se cachea por proceso.** `get_road_router()` lo construye una vez
y lo guarda en una global. Cambiar la configuración **no** lo reconstruye: hace
falta reiniciar. Es deliberado —montar un cliente por tramo sería caro— pero es
la causa más común de "ya puse la URL y sigue diciendo que no hay motor", y ahora
está documentado en el propio docstring.

### 4.3 Lo que sólo encontró la API real — `CONFIRMED`

**El adaptador no funcionaba.** La primera versión mandaba
`instructionsType=none`, que parece razonable y que **los 13 tests unitarios
aceptaron sin rechistar** —uno de ellos llegaba a afirmarlo como correcto—.
TomTom respondió:

```
BAD_INPUT: Invalid InstructionsType value: [none]
```

Sólo acepta `coded`, `text` y `tagged`; para no recibir instrucciones el
parámetro **se omite**, y con `routeRepresentation=summaryOnly` tampoco
vendrían. Corregido, con el comentario en el código para que nadie lo vuelva a
añadir "por claridad", y el test unitario invertido para que ahora exija su
ausencia.

Es exactamente lo que este reporte decía que un doble no puede demostrar, y
ocurrió a la primera llamada. Un doble confirma la lógica; sólo el motor real
confirma que el adaptador está bien escrito.

### 4.4 Evidencia de la ejecución real

Coordenadas de Athens, Georgia —la zona del entorno de pruebas—:

| Comprobación | Medido |
|---|---|
| Ruta A→B | **4.976 m** (3,092 mi) por carretera |
| Línea recta | 4.239,37 m (2,634 mi) |
| Factor de desvío | **1,174** — la vía supera a la recta, como debe |
| Determinismo | misma pregunta dos veces → **4976 = 4976**. `traffic=false` funciona |
| Coordenadas invertidas | `MAP_MATCHING_FAILURE`, nombrando el origen. **Permanente** |
| Punto en el Atlántico | `MAP_MATCHING_FAILURE`. **Permanente** |
| Clave inválida | `401`, **permanente**, y la clave **no aparece** en el mensaje |
| `provider` / `method` | `tomtom` / `car/fastest/no-traffic`; `formatVersion` 0.0.12 |

Las cinco quedan como tests en `test_route_routing_live.py`, tras la puerta
`TOMTOM_API_KEY`, igual que los de OSRM y Valhalla.

### 4.5 Errores propios durante la ejecución

Se reportan porque ocurrieron.

**Inventé `app.utils.time.utc_now`.** No existe. El proyecto usa
`datetime.now(timezone.utc)` directamente. `ModuleNotFoundError` al primer
import.

**Pasé `session=` a `record_event`.** Su firma no lo acepta
(`company_id, entity_type, entity_id, action, actor_user_id, summary, changes,
reason`). Corregido llamándola fuera de la transacción, como hace el motor.

Los dos son el mismo patrón: escribir contra la memoria en vez de contra el
código. Los dos salieron en la primera ejecución.

---

## 5. Validación técnica

| Comprobación | Resultado |
|---|---|
| `uv run python -c "import app.main"` | **PASS** |
| `tests/test_tomtom_router.py` | **PASS** — 13/13 |
| `tests/integration/test_reprocess_failed_mileage.py` | **PASS** — 5/5 |
| `tests/test_permission_catalog.py` | **PASS** — 7/7 |
| Regresión del lote completo | **PASS** — **53 passed, 1 skipped**, `exit 0` (tras la corrección) |
| Comando en modo simulación contra la base local | **PASS** — corre, 0 candidatos (base vacía) |
| **Contra la API real de TomTom** | **PASS** — 5 tests, `6 passed, 9 skipped in 11.12s` |
| Migraciones | `NOT APPLICABLE` — sin cambio de esquema |
| `npm run check` | `NOT APPLICABLE` — sin cambio de frontend |

### Lo que los tests cubren, y lo que no

Los 13 del adaptador fijan la URL con `lat,lon`, los parámetros
(`traffic=false`, `routeRepresentation=summaryOnly`), la lectura de
`lengthInMeters`, la redacción de la clave en los errores y la clasificación
transitorio/permanente de 503, 429, 403, 401, `MAP_MATCHING_FAILURE` y
`NO_ROUTE_FOUND`.

Los 5 de la reposición cubren las dos formas de equivocarse, que son opuestas:
reponer **de menos** deja viajes sin kilometraje para siempre; reponer **de más**
gasta intentos en viajes a los que les falta un waypoint. También el aislamiento
entre empresas, el rango de fechas, que la simulación no escriba y que la
auditoría quede.

**Ninguno de ellos demuestra que TomTom conteste lo que su documentación dice.**
Eso sólo lo demuestra una clave real, y es lo que queda pendiente.

---

## 6. Estimación de lo que falta

| Tarea | Estado | Volumen medido | Complejidad | Horas-agente |
|---|---|---|---|---|
| `TomTomRouter` + cableado | `COMPLETED` | 285 LoC en `routing.py` | integración terceros | 3,0 |
| Integración `road_routing` | `COMPLETED` | 91 LoC | backend/dominio | 0,5 |
| Comando de reposición | `COMPLETED` | 215 LoC | backend/dominio | 1,5 |
| Tests (18) | `COMPLETED` | 330 LoC | integración | 3,5 |
| **Entregado** | | **921 LoC** | | **8,5** |

Pendiente:

| Tarea | Estado | Horas-agente |
|---|---|---|
| Verificar los términos de TomTom (§4.1) | `PENDING` — **no es trabajo de Development** | — |
| Probar con clave real y registrar las cifras | `COMPLETED` | — |
| Comprobación de salud `road_routing` | `PENDING` | 1,5 |
| Invalidar la caché del router al guardar la integración | `PENDING` | 1,0 |
| Tests del cableado integración → adaptador | `PENDING` | 1,5 |
| Test que exija comprobación de salud a toda integración | `PENDING` | 0,5 |
| Reponer los fallidos del entorno de pruebas | `PENDING` — espera decisión de rango | 0,5 |
| **Subtotal** | | **5,0** |

Coeficientes: integración de terceros **80-100 LoC/h** (se usó 90),
backend/dominio **150-200 LoC/h** (se usó 175). Margen **+30%** por integración
de terceros.

**Total pendiente con margen: 6,5 horas-agente.**

---

## 7. Git

| | |
|---|---|
| Rama | `feature/tomtom-routing-adapter`, desde `dev` |
| Commits | 1 |
| Push | sí |
| Árbol | limpio |
| MR | ver §9 |
| Fusionado | **no** |

---

## 8. Trabajo restante y acción operativa

1. **CER verifica los términos de TomTom** sobre almacenamiento permanente de
   distancia derivada. Si no lo permiten, esto no se usa con datos reales.
2. **Crear la clave** en el portal de TomTom, restringirla a Routing API y a las
   direcciones de salida de CER.
3. **Guardarla** por la pantalla de integraciones, no por variable de entorno.
4. **Reiniciar el proceso.** Sin esto sigue montado `UnconfiguredRouter`.
5. **Verificar** que los viajes nuevos calculan.
6. **Decidir el rango** y ejecutar la reposición, primero en simulación.

Nada de 2 a 6 lo hace este cambio: es despliegue y decisión.

---

## 9. Siguiente paso, sin empezarlo

Añadir la sección de TomTom al test de routing real
(`tests/integration/test_route_routing_live.py`), que hoy sólo cubre OSRM y
Valhalla. Necesita una clave, así que espera a §8.2.

**Nota de secuencia:** señalé que convenía esperar a la certificación de RTE06
antes de meter un motor nuevo, y CER decidió avanzar. Por eso va en rama
separada y **no toca nada del MR !29**, que sigue abierto esperando
certificación. Los dos se pueden revisar por separado.

MR abiertos: **!24**, **!29**, **!30**, y el de este cambio.
