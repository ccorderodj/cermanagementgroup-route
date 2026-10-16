# CER Route — RTE10-A02 · Puerta obligatoria de permiso de ubicación
## Reporte 001

**Instrucción:** `CER_ROUTE_RTE10_A02_MANDATORY_LOCATION_GATE_INSTRUCTIONS_002.md`
**Rama:** `feature/rte10-a02-location-permission-gate` (desde `dev`)
**Fecha:** 2026-10-07

---

## 1. Resultado ejecutivo

La puerta está implementada y la distinción que gobierna el checkpoint se respeta en los dos sentidos:

```text
permiso denegado  ->  se bloquea        (una decisión de la persona)
sin señal         ->  NO se bloquea     (una condición del entorno)
```

Lo que lo hace defendible y no una colección de comprobaciones sueltas es que la guarda vive en **un solo sitio**: `enqueueAction`, el punto por el que pasan **todas** las acciones operativas del producto. Ponerla en cada pantalla habría dejado la puerta abierta en la siguiente que alguien añadiera.

Tres cosas que conviene leer aunque el resultado sea verde:

* **Este checkpoint deroga un contrato certificado de RTE06**, y no lo hice en silencio. El AC-8 decía que «con el permiso denegado, el día entero funciona». §2 lo supersede. Reorienté ese test a la mitad que sigue vigente —sin señal— y dejé la derogación escrita en su docstring.
* **Mi primera implementación introdujo una carrera real**, no sólo un test rojo: consultaba el permiso del navegador antes de escribir en IndexedDB en **todas** las acciones, ensanchando la ventana entre «la pantalla avanzó» y «la acción es durable». La corrección fue dejar de consultar donde no hace falta.
* **El servidor no puede ver el permiso de nadie.** No finjo lo contrario. §11 queda cubierto con lo más fuerte que la arquitectura permite de verdad, y la frontera de confianza está escrita en §11 de este reporte.

**446 tests · 0 fallos · 0 errores · 1 saltado.**

---

## 2. Política anterior frente a la nueva

| | Antes (RTE06) | Ahora (RTE10-A02) |
|---|---|---|
| Permiso **denegado** o `prompt` | el día funcionaba entero, en silencio | **bloqueado**: puerta `Location Required` |
| Permiso concedido, **sin señal** | funcionaba, en silencio | **igual**: funciona, en silencio |
| Evidencia Fresh/Cached/Recovery/Missing | intacta | **intacta** |
| Cola offline | intacta | **intacta** |

La derogación es **sólo** sobre la denegación del permiso. Todo lo demás se conserva, y hay tests que lo fijan.

### La derogación, declarada

`tests/e2e/test_rte06_silent_capture_browser.py::test_the_day_runs_normally_with_location_denied` codificaba el AC-8 de RTE06. Hoy es falso por decisión de producto.

**No se borró.** Se reorientó a `test_the_day_runs_normally_without_a_location_fix`, con el permiso **concedido** y sin coordenada — el caso de la nave industrial, que §9 preserva palabra por palabra. El caso denegado lo cubre ahora el suite nuevo de la puerta. El docstring explica la derogación para quien lo lea dentro de un año.

---

## 3. Modelo de estado del permiso

```text
granted      -> operativo
prompt       -> bloqueado   (nadie ha dicho que sí todavía)
denied       -> bloqueado
unavailable  -> se SONDEA, no se asume
```

`prompt` del lado bloqueado es exigencia de §2.1, y es correcto: operar con un permiso que nadie concedió sería operar sin permiso.

### `unavailable` es el caso que obliga a sondear

`navigator.permissions.query({name:'geolocation'})` no existe en todos los navegadores — Safari de iOS no lo soportó durante años, y es un navegador **de campo**. Ahí la API devuelve `unavailable`, que **no significa denegado**: significa que no se sabe.

Tratarlo como denegado dejaría a todo ese parque fuera del producto. Tratarlo como concedido abriría la puerta que este checkpoint cierra. Así que no se asume: se pregunta al GPS, y su error lo dice sin ambigüedad.

```text
getCurrentPosition resuelve        -> hay permiso
error 1  PERMISSION_DENIED         -> NO hay permiso
error 2  POSITION_UNAVAILABLE      -> hay permiso, no hay señal
error 3  TIMEOUT                   -> hay permiso, no hay señal
```

Los códigos 2 y 3 son exactamente el caso que §2.2 prohíbe bloquear, y por eso resuelven a `granted`. **El sondeo usa `maximumAge: Infinity`**: vale cualquier punto cacheado por viejo que sea, porque no se busca la posición — se busca el veredicto.

---

## 4. La pantalla

```text
            Location Required

  CER Route requires location access to use My Route.

          [  Enable Location  ]
```

Y las tres ausencias que §5.1 exige, cada una verificada en navegador real:

| | |
|---|---|
| No se puede descartar | ✔ |
| Sin «continuar sin ubicación» | ✔ |
| **Sin «comprobar de nuevo»** | ✔ |

La última tiene motivo: un botón de reintentar traslada a la persona el trabajo de vigilar, y se equivoca justo cuando importa — el permiso se concede en los ajustes del sistema, **fuera de la pestaña**, y al volver la pantalla ya debería saberlo.

### La puerta no tapa una jornada abierta

Decisión de diseño que §8 obliga y que es fácil equivocar: con jornada abierta la pantalla **se muestra**, para poder cerrarla. Lo que bloquea entonces no es la pantalla sino la guarda por acción.

```text
sin jornada  ->  puerta total        (no hay nada que cerrar)
con jornada  ->  pantalla normal     (se puede llegar, completar, terminar)
                 + guarda por acción (no se puede empezar nada nuevo)
```

Una puerta a pantalla completa sobre una jornada abierta habría impedido terminar el día. El supervisor quedaría atrapado y el registro, mintiendo.

---

## 5. `Enable Location`

`getCurrentPosition` es lo único que abre el diálogo nativo; la Permissions API sólo consulta.

Y si el navegador ya marcó el sitio como denegado, **no vuelve a preguntar**: devuelve el error al instante. En ese caso la pantalla no simula que preguntó — explica dónde se cambia:

> *Your browser has blocked location for this site, so it will not ask again. Open the site settings — the icon at the left of the address bar — allow Location, and this screen will continue on its own.*

Se detecta comparando el estado **antes** y el resultado **después**: `denied → denied` significa que el diálogo no llegó a abrirse; `prompt → denied` significa que la persona dijo que no.

---

## 6. Cuándo se reevalúa

Cuatro vías, y ninguna basta sola:

| Vía | Qué cubre | Por qué no basta sola |
|---|---|---|
| `PermissionStatus.onchange` | el cambio en el momento | no existe en todos los navegadores |
| `visibilitychange` | volver a la pestaña | revocar se hace **fuera** de la pestaña |
| `focus` | cambiar de ventana sin ocultar | — |
| `pageshow` | vuelta desde la caché atrás/adelante | ahí no hay recarga |

Más la reevaluación **en el momento de actuar**: `enqueueAction` lee el permiso al abrir trabajo nuevo, no un valor en memoria. §13 pide expresamente no fiarse de un valor cacheado; esto es lo que convierte esa exigencia en código.

---

## 7. Matriz de acciones operativas

Verificada contra el código, no contra los nombres de los botones (§14 lo pide así).

| Acción (`kind`) | Endpoint | ¿Abre? | ¿Exige permiso? | ¿Permitida si se pierde a mitad? |
|---|---|---|---|---|
| `worksession.start` | `POST /worksessions` | sí | **sí** | no |
| `trip.plan` | `POST /trips` | sí | **sí** | no |
| `trip.start` | `POST /trips/{}/start` | sí | **sí** | no |
| `trip.change_plan` | `POST /trips/{}/change-plan` | sí | **sí** | no |
| `activity.start` | `POST /trips/{}/activity/start` | sí | **sí** | no |
| `trip.arrive` | `POST /trips/{}/arrive` | no, cierra | no | **sí** |
| `activity.complete` | `POST /trips/{}/activity/complete` | no, cierra | no | **sí** |
| `activity.leave` | `POST /trips/{}/activity/leave` | no, cierra | no | **sí** |
| `worksession.end` | `POST /worksessions/{}/end` | no, cierra | no | **sí** |

`trip.arrive` incluye la llegada a casa: volver a casa cierra su viaje, no abre nada.

**La matriz es una lista cerrada y hay una red que la vigila.** `tests/test_operational_action_matrix.py` lee las tres fuentes —la clasificación del cliente, las llamadas a `enqueueAction` y los decoradores de los routers— y exige que digan lo mismo. Una acción nueva sin clasificar rompe la suite; una que abra trabajo y pierda su guarda, también.

---

## 8. Revocación a mitad y excepción de cierre

```text
permiso revocado con jornada abierta
   -> llegar          ✔ permitido
   -> completar       ✔ permitido
   -> marcharse       ✔ permitido
   -> terminar día    ✔ permitido
   -> empezar viaje   ✘ bloqueado
   -> cambiar plan    ✘ bloqueado
   -> nueva parada    ✘ bloqueado

tras cerrar lo abierto, sin permiso -> puerta
```

La excepción existe para no atrapar registros abiertos. **No es un camino para empezar trabajo**, y hay un test dedicado a esa frontera: `test_tras_cerrar_lo_abierto_no_se_puede_abrir_nada_nuevo`. Sin él, un refuerzo que dejara pasar todo tras la primera llegada pasaría los demás.

---

## 9. Señal, recuperación y offline

Intactos. No se tocó `location.ts`, ni la cola, ni la política de evidencia.

* `Fresh → Cached → Recovery → Missing` sin cambios.
* Ningún mensaje nuevo por falta de señal: el test que lo vigila sigue verde, ahora bajo permiso concedido.
* Ninguna coordenada fabricada: `location_fix == 0` cuando no hay punto utilizable.
* `no hay Internet` y `permiso denegado` no se confunden: la guarda mira el permiso y no la red.

**El test que vale por todos:** `test_permiso_concedido_sin_senal_NO_bloquea`, en navegador real, con permiso concedido y **sin coordenada**. Si la puerta se cerrara por falta de señal, media plantilla se quedaría sin trabajar — y sería invisible en cualquier test que conceda permiso *y* coordenadas a la vez.

---

## 10. Offline

La aserción del permiso se guarda **con la acción, al encolarla**, y se envía al vaciar la cola:

```ts
locationPermission: permiso   // en la acción, no al enviar
'X-Location-Permission': accion.locationPermission
```

Es deliberado y es la única forma correcta: una acción tomada en una nave sin cobertura puede enviarse horas después. Releer el permiso al vaciar contestaría otra pregunta — *«¿tiene permiso ahora?»*— cuando la que importa es *«¿lo tenía cuando trabajó?»*.

---

## 11. Refuerzo del servidor y frontera de confianza

**Lo que el servidor no puede hacer, dicho sin rodeos:** el permiso vive en el navegador y en el sistema operativo del dispositivo. El servidor no puede verlo. Cualquier cosa que el cliente envíe sobre su propio permiso es una **afirmación suya, no una prueba**. Un cliente modificado a mano puede enviar `granted` siendo falso.

Eso es inevitable, y es la misma frontera que ya tiene toda la evidencia de ubicación — el navegador podría mentir sobre sus coordenadas — que el producto ya trata declarando la procedencia en vez de pretendiendo certeza.

**Lo que sí se hace**, que es lo más fuerte que la arquitectura permite de verdad:

1. **Se exige la afirmación.** Una transición que abre trabajo sin la cabecera, o con un valor distinto de `granted`, se rechaza con **403**. Ausencia no es permiso: un cliente que no pasó por la puerta no entra por descuido.
2. **Se audita.** Cada intento bloqueado queda en `audit_event` con el actor y el estado declarado.
3. **No se debilita la puerta del cliente** por esta limitación, que §11 prohíbe expresamente.

Lo que esta puerta sí cierra es el caso real: el supervisor cuyo permiso está revocado y cuyo cliente, legítimo, no puede abrir trabajo nuevo.

---

## 12. Recarga, segundo plano y multidispositivo

| | |
|---|---|
| **Recarga** | se reevalúa; sin permiso, puerta. Verificado en navegador |
| **Segundo plano** | `visibilitychange`, `focus` y `pageshow` |
| **Multidispositivo** | el permiso es del navegador; cada dispositivo pasa su propia puerta. No se almacena nada en el servidor que pudiera heredarse |

---

## 13. Auditoría

| Hecho | Dónde queda |
|---|---|
| Intento bloqueado de abrir trabajo | `audit_event`, `location_permission/blocked`, con el estado declarado |
| Permiso concedido / denegado al capturar | `location_fix.permission_state` y `missing_location_event.permission_state` — ya existían |
| Cierre con el permiso perdido | el evento de cierre normal, sin cabecera de permiso |

No se añaden coordenadas a los registros de auditoría. La falta de señal **no** genera un evento nuevo: sigue el modelo de evidencia existente, como §12 pide.

---

## 14. Tests y regresión

**446 tests · 0 fallos · 0 errores · 1 saltado**, por lotes separados.

### Nuevos

| Archivo | Tests | Qué fija |
|---|---:|---|
| `tests/integration/test_location_permission_gate.py` | 10 | el refuerzo del servidor y la excepción de cierre |
| `tests/test_operational_action_matrix.py` | 6 | que las dos mitades no se separen |
| `tests/e2e/test_location_permission_gate_browser.py` | 6 | la puerta tal como la ve el supervisor |

### Discriminantes, probado por mutación

§16 exige que quitar la puerta haga fallar los tests. Medido:

```text
puerta del servidor neutralizada   -> 6 de 10 fallan
    y las 4 que siguen pasando son justo las de la excepción de cierre,
    que deben seguir pasando

guarda retirada de un endpoint     -> la matriz lo detecta y lo nombra
```

### Dos defectos míos, encontrados por la regresión

**1 · Una carrera real, no un test frágil.** `test_an_execution_command_survives_a_disconnection` falló de forma intermitente. Lo aislé sustituyendo la lectura del permiso por una constante: con eso pasaba.

El problema iba más allá del test. La cola durable promete que *«aceptado por la interfaz» y «durable» son la misma cosa*, y yo estaba añadiendo una consulta al navegador **antes** de escribir en IndexedDB, en **todas** las acciones.

La corrección no fue apretar el test: fue dejar de consultar donde no hace falta.

```ts
if (abreTrabajoNuevo(kind)) {        // sólo si abre trabajo nuevo
    const actual = await leerPermisoOperativo();
    ...
}
```

Las acciones de cierre ya no consultan nada — y son justo las que tienen que funcionar con la batería muriéndose y sin cobertura. **4 de 4 ejecuciones estables** tras el cambio.

**2 · Los tests de navegador existentes no concedían geolocalización**, así que mi puerta los bloqueaba a todos y cada aserción agotaba su espera de 20 s. Corregido en `abrir_sesion`, el helper que todos comparten: concede permiso **y** coordenada, porque conceder sin posición deja cada captura esperando a un GPS que nunca responde. Los tests de la puerta pasan `conceder_ubicacion=False` — ahí la ausencia de permiso *es* la prueba.

### Dos falsos positivos, descartados con evidencia

Al interrumpir una ejecución larga dejé la base de tests a medio recrear, y eso produjo un **401** y luego **17 errores** (`duplicate key ... (typname)=(alembic_version)`). Los perseguí hasta el mensaje concreto en vez de darlos por intermitentes: eran el esquema, no el producto. Restaurada la base, los mismos lotes pasan enteros.

### Lotes

| Lote | Tests | Fallos | Err | Skip |
|---|---:|---:|---:|---:|
| `test_location_permission_gate.py` (nuevo) | 10 | 0 | 0 | 0 |
| `test_operational_action_matrix.py` (nuevo) | 6 | 0 | 0 | 0 |
| `test_work_sessions.py` | 42 | 0 | 0 | 0 |
| `test_trips.py` | 66 | 0 | 0 | 0 |
| `test_activities.py` | 37 | 0 | 0 | 0 |
| `test_route_location_evidence.py` | 39 | 0 | 0 | 0 |
| `test_route_exact_correlation.py` | 14 | 0 | 0 | 0 |
| `test_route_mileage_engine.py` | 24 | 0 | 0 | 1 |
| `test_mileage_cross_surface.py` | 8 | 0 | 0 | 0 |
| `test_odometer.py` | 37 | 0 | 0 | 0 |
| `test_odometer_end_work.py` | 11 | 0 | 0 | 0 |
| `test_live_today.py` | 15 | 0 | 0 | 0 |
| `test_activity_explorer.py` | 17 | 0 | 0 | 0 |
| `test_page_wiring.py` · `test_navigation_wiring.py` | 42 | 0 | 0 | 0 |
| `test_public_surface.py` · `test_permission_catalog.py` | 21 | 0 | 0 | 0 |
| **navegador** `test_location_permission_gate_browser.py` (nuevo) | 6 | 0 | 0 | 0 |
| **navegador** `test_rte05_workbench_browser.py` | 24 | 0 | 0 | 0 |
| **navegador** `test_trip_and_odometer_browser.py` | 6 | 0 | 0 | 0 |
| **navegador** `test_activity_execution_browser.py` | 15 | 0 | 0 | 0 |
| **navegador** `test_rte06_bounded_queue_browser.py` | 2 | 0 | 0 | 0 |
| **navegador** `test_rte06_silent_capture_browser.py` | 2 | 0 | 0 | 0 |
| **navegador** `test_rte06_end_restoration_browser.py` | 2 | 0 | 0 | 0 |

* `import app.main` → **ok**
* **Frontend** `npm run check` → typecheck **0 errores**, lint **0 errores**
* **Frontend** `npm run build:prod` → compilado; los tests de navegador corren contra ese bundle
* **Migraciones** → `NOT APPLICABLE`

---

## 15. Esperado → Implementado → Evidencia → Hueco

| # | Criterio de §15 | Estado | Evidencia |
|---:|---|---|---|
| 1 | My Route bloqueado sin permiso | **VALIDATED** | navegador |
| 2 | La pantalla dice que hace falta ubicación | **VALIDATED** | navegador |
| 3 | La acción principal es `Enable Location` | **VALIDATED** | navegador |
| 4 | Sin descartar ni continuar sin ubicación | **VALIDATED** | navegador, aserción de ausencia |
| 5 | Sin `Check Again` | **VALIDATED** | navegador, aserción de ausencia |
| 6 | Restauración automática al conceder | **VALIDATED** | navegador |
| 7 | Start Work exige permiso | **VALIDATED** | servidor + cliente |
| 8 | Toda transición nueva exige permiso | **VALIDATED** | §7, matriz con red |
| 9 | Revocar impide la siguiente acción nueva | **VALIDATED** | servidor |
| 10 | Un viaje abierto se puede cerrar | **VALIDATED** | servidor |
| 11 | Una parada abierta se puede completar | **VALIDATED** | servidor |
| 12 | Una jornada activa se puede terminar | **VALIDATED** | servidor |
| 13 | Tras cerrar, vuelve la puerta | **VALIDATED** | servidor |
| 14 | Reevaluación en recarga/retorno/preflight | **VALIDATED** | §6, navegador |
| 15 | Permiso + sin GPS **no** bloquea | **VALIDATED** | navegador, test dedicado |
| 16 | Ningún aviso nuevo por falta de señal | **VALIDATED** | `rte06_silent_capture` |
| 17 | Fresh/Cached/Recovery/Missing intactos | **VALIDATED** | 39 tests de evidencia |
| 18 | Offline intacto | **VALIDATED** | cola y reenvío verdes |
| 19 | Ninguna ubicación fabricada | **VALIDATED** | `location_fix == 0` sin punto |
| 20 | Sin rastreo fuera del trabajo | **VALIDATED** | no se añadió ningún seguimiento |
| 21 | Superficies de administración intactas | **VALIDATED** | sólo se tocó My Route |
| 22 | Riesgo de bypass del API atendido | **VALIDATED** | §11, con su frontera declarada |
| 23 | Regresiones existentes verdes | **VALIDATED** | §14 |
| 24 | Sin `Partial`/`Gap`/`Blocked` sin explicar | **VALIDATED** | §16 |

**Hueco dentro del alcance: ninguno.**

---

## 16. Asuntos restantes

**Dentro del alcance: ninguno.**

**Decisión de producto consumada, para que CER la confirme:** la derogación del AC-8 de RTE06 (§2 de este reporte). No es un hueco — §2 de la instrucción la ordena — pero cambia un contrato certificado y merece un «sí» explícito.

**Observación declarada:** la frontera de confianza del servidor (§11). No es una carencia de la implementación, es una propiedad de la plataforma, y queda escrita para que nadie la descubra como sorpresa.

**Deuda preexistente, ya reportada en el MR !66:** `test_rte04_closure_browser::test_a_rejected_end_work_does_not_come_back_from_the_queue` falla en `dev` desde antes de este checkpoint. No se incluyó en esta regresión porque no lo toca este delta.

---

## 17. Estado propuesto

```text
RTE10-A02 MANDATORY LOCATION PERMISSION GATE COMPLETE / READY FOR CER VALIDATION
```

No se declara cerrado: la certificación es de CER.

---

## 18. Estimación del esfuerzo

| Componente | Líneas |
|---|---:|
| `shared/lib/location/permission.ts` | 192 |
| `shared/lib/location/operationalActions.ts` | 80 |
| `features/RouteLocationGate/ui/LocationGate.tsx` | 128 |
| `routers_api/location/permission_gate.py` | 104 |
| `tests/integration/test_location_permission_gate.py` | 330 |
| `tests/test_operational_action_matrix.py` | 181 |
| `tests/e2e/test_location_permission_gate_browser.py` | 218 |
| Modificados (10 archivos) | +417 / −253 |
| **Total** | **≈ 1 650 / −253** |

| Tarea | Estado | Complejidad | Horas-agente |
|---|---|---|---|
| Auditar la arquitectura de permiso, cola y comandos | `DONE` | análisis | 1,2 |
| Módulo de permiso, con el sondeo para `unavailable` | `DONE` | UI/navegador | 1,6 |
| Registro cerrado y guarda en `enqueueAction` | `DONE` | frontend | 1,0 |
| Aserción en la cola durable y cabecera al enviar | `DONE` | frontend | 0,6 |
| Puerta del servidor en las cinco transiciones | `DONE` | backend | 0,9 |
| `LocationGate` y su conexión a My Route | `DONE` | UI | 1,4 |
| Tests de integración (10) + mutación | `DONE` | integración | 2,6 |
| Matriz de acciones (6) + mutación | `DONE` | integración | 1,5 |
| Tests de navegador (6) | `DONE` | UI/navegador | 2,8 |
| **Diagnóstico y corrección de la carrera** | `DONE` | diagnóstico | 1,8 |
| Derogación del AC-8 y reorientación de su test | `DONE` | producto | 0,9 |
| Falsos positivos de la base de tests, descartados | `DONE` | diagnóstico | 0,8 |
| Regresión por lotes (446 tests) + builds | `DONE` | ejecución | 2,0 |
| Reporte | `DONE` | documentación | 1,0 |
| **Subtotal ejecutado** | | | **20,1** |
| Margen de riesgo (+50 %, automatización de navegador) | | | **+10,1** |
| **Total del delta** | | | **≈ 30,2 h-agente** |

---

## 19. Siguiente paso

Revisión de CER y validación de campo, con especial atención a dos cosas que sólo el terreno puede confirmar:

1. **Safari de iOS**, donde la Permissions API puede no existir y manda el sondeo de §3.
2. **Un supervisor dentro de una nave**, para confirmar que la falta de señal no le bloquea — que es el riesgo que este checkpoint tenía que evitar y no causar.

**No se inicia Reports. No se inicia RTE09. No se reanuda RTE10-A01. No se tocan Today / Live ni Activity Explorer.**
