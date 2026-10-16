# CER Route — RTE10-A02 · Corrección tras validación de campo
## Reporte 002

**Origen:** reporte de campo sobre el MR !67 — *«cuando la ubicación no está activada no se muestra la puerta, y la función del sistema no está funcionando como se espera»*
**Rama:** `fix/rte10-a02-gate-field-defects` (desde `dev`, con el !67 ya desplegado)
**Fecha:** 2026-10-07
**Corrige** `CER_ROUTE_RTE10_A02_MANDATORY_LOCATION_GATE_REPORT_001.md`.

---

## 1. Resultado ejecutivo

**El reporte de campo era correcto, y los defectos eran míos.** El MR !67 pasó 446 tests y falló en producción por cuatro motivos, todos de los que un test de laboratorio no ve si no se le pregunta exactamente lo que pasa en la calle.

| # | Defecto | Efecto en campo | Evidencia |
|---|---|---|---|
| **1** | La puerta se fiaba de la Permissions API | Con la ubicación **del teléfono** apagada, la puerta **no aparecía** | **39 %** de las denegaciones reales en producción |
| **2** | Con jornada abierta la puerta se ocultaba | Pantalla normal, botones que fallaban, sin `Enable Location` | casi todos los supervisores tienen jornada abierta |
| **3** | Un 403 de permiso se trataba como rechazo definitivo | **Pérdida de datos**: lo encolado sin cobertura antes del despliegue se borraba | reproducido en navegador |
| **4** | Parada sin empezar + sin ubicación | El supervisor quedaba **atrapado**, sin ninguna salida | modelo de estados |

Los tres primeros están **reproducidos contra la versión en producción**: los tests nuevos fallan con el !67 y pasan con esta corrección. El cuarto lo resolvió una decisión de CER.

**445 tests · 0 fallos · 0 errores · 1 saltado.**

---

## 2. Defecto 1 — La ubicación del teléfono apagada

### Qué pasaba

La Permissions API describe el permiso **del sitio**. No sabe nada de la ubicación **del dispositivo**. Con el interruptor de ubicación de Android o los Servicios de Localización de iOS apagados, el sitio sigue «concedido» y `getCurrentPosition` responde `PERMISSION_DENIED` igual.

La primera versión de la puerta leía la API, veía `granted` y dejaba pasar. Es exactamente lo que el supervisor describe como *«tengo la ubicación desactivada»*.

### Medido en producción

```text
denegaciones reales al pedir posición: 119

  Permissions API = denied    ->  62   (52 %)
  Permissions API = granted   ->  46   (39 %)   <- la puerta no aparecía
  Permissions API = prompt    ->  11   ( 9 %)
```

### La corrección

`granted` ya no se cree sin verificar: se pide una posición. Y aquí hay una sutileza que costó un segundo intento (§6): **no se espera al GPS**.

```text
un "no" del sistema    ->  llega en milisegundos (es una autorización)
la falta de señal      ->  es una espera (el GPS busca satélites)
```

Así que se espera sólo **500 ms** a que llegue un «no». Si no llega, hay acceso — y lo que tarde el punto es asunto del modelo de evidencia, no de la puerta.

| Lo que responde el GPS | Veredicto |
|---|---|
| un punto | acceso |
| `code 1` PERMISSION_DENIED | **puerta** |
| `code 2` POSITION_UNAVAILABLE | acceso — es falta de señal, §2.2 |
| `code 3` TIMEOUT | acceso — es falta de señal, §2.2 |
| nada en 500 ms | acceso — una denegación habría llegado ya |

`prompt` y `denied` se respetan **sin sondear**: sondear en `prompt` abriría el diálogo nativo sin que la persona lo pidiera, y §7 lo prohíbe.

---

## 3. Defecto 2 — La jornada ya abierta

### Qué pasaba

La primera versión ocultaba la puerta cuando había una jornada abierta, para que se pudiera cerrar lo abierto. El resultado fue el peor posible: el supervisor veía la pantalla **normal**, con «What's next?» y sus siete opciones; pulsaba una y recibía un error, sin ningún `Enable Location`.

§5.1 lo prohíbe en una frase: *el supervisor no puede ver un estado normal y accionable*.

### La corrección

Sin acceso a la ubicación, la puerta **siempre** aparece. Con algo abierto, va **encima**, y debajo queda sólo lo que **cierra**:

| Fase | Se retira (abre) | Se mantiene (cierra) |
|---|---|---|
| Jornada abierta | «What's next?» y las siete opciones · lectura de inicio | **End Work** |
| Viaje preparado sin salir | Start Trip · lectura de inicio | **End Work** *(nuevo aquí)* |
| En ruta | Change Plan | **Arrived** |
| En la parada | — | Start Activity · Complete · Leave |

La puerta compacta dice además: *«You can still finish what is already open below. Nothing new can start until location is on.»*

Y si la ubicación se apaga **con la página delante** —desde la persiana de Android, que no siempre dispara ningún evento—, el primer intento de abrir trabajo lo descubre y la puerta aparece en ese mismo instante, en vez de un error sobre una pantalla que parece normal.

---

## 4. Defecto 3 — La pérdida de datos

### Qué pasaba

La cola durable trata cualquier 4xx como definitivo y **borra** la acción. Es correcto para un 409 o un 422, que dirán lo mismo dentro de una hora. No lo es para este caso:

```text
un supervisor trabaja sin cobertura en una nave
   -> la acción se encola con el cliente VIEJO, sin aserción de permiso
se despliega el !67
   -> la acción se envía, el servidor responde 403
   -> la cola la BORRA
   -> y por el orden de la cola, todo lo que dependía de ella detrás
```

Trabajo de campo real, perdido por un cambio de versión. §11 exigía compatibilidad con la cola offline.

### La corrección

1. **El servidor marca su rechazo** con la cabecera `X-Location-Permission-Required: true`.
2. **La cola la reconoce** y conserva la acción: se detiene en ella —preservando el orden— y la reintenta cuando el permiso vuelve.
3. **Las acciones heredadas** se reenvían con el permiso verificado del momento del envío.

Se reconoce por la cabecera y no por el texto del mensaje: cambiar una frase no puede convertir una espera en un borrado.

### La frontera, declarada

Para las acciones encoladas **antes** de RTE10-A02, la aserción describe el momento del envío, no el de la acción: ese dato no se guardó y ya no se puede saber. La alternativa —enviarlas sin nada— era borrarlas. Es una frontera acotada a lo que estaba en los teléfonos el día del despliegue.

---

## 5. Defecto 4 — La parada sin empezar: decisión de CER

### El hecho

Un supervisor llega a una parada, todavía no pulsa `Start Activity`, y pierde la ubicación.

- No puede empezar la actividad: la matriz de §14 la trataba como apertura.
- No puede terminar la jornada: el servidor exige resolver la parada primero (`409 — Finish the work at your current stop`).
- No existe «marcharse sin empezar».

**Atrapado.** §8 lo prohíbe.

### La decisión

**CER decidió que `Start Activity` es un paso de cierre.** El motivo está en el modelo de estados, que §14 pedía validar en vez de fiarse del nombre del botón: una actividad **sólo se puede empezar en un viaje que ya llegó**, así que nunca abre trabajo nuevo — siempre es el primer paso para cerrar un viaje abierto.

| Acción | Antes (!67) | Ahora |
|---|---|---|
| `activity.start` | abre · exige permiso | **cierra · no lo exige** |

La evidencia de esa parada queda como `Missing`, que es la verdad. No se inventa nada.

---

## 6. Un tropiezo mío dentro de la corrección

La primera versión de la corrección del defecto 1 **esperaba al GPS** hasta agotar su tiempo (4 s). Bajo techo eso son 4 segundos al cargar la pantalla y otros 4 en cada `Start Trip`.

Lo detectó un test certificado de RTE06:

```text
test_no_blocking_spinner_waits_for_location
  el workbench tardó 9.5s: parece estar esperando a la ubicación,
  y §36 prohíbe que la acción espere
```

Es exactamente la nave industrial que §2.2 no permite frenar. Lo resolvió la ventana de 500 ms de §2.

---

## 7. Dos tests que no probaban lo que su nombre decía

`test_the_day_runs_normally_without_a_location_fix` y `test_permiso_concedido_sin_senal_NO_bloquea` dicen simular **sin señal**, y lo hacían concediendo el permiso sin fijar coordenadas — dejando la respuesta al GPS real de la máquina de pruebas.

Medido en esa máquina:

```text
1.ª petición:  code 1 (denegado)  en 156 ms
siguientes:    code 3 (timeout)   en ~4000 ms
```

La máquina tiene la ubicación del sistema apagada, así que esos tests simulaban **«ubicación del dispositivo apagada»**, no «sin señal» — y con la corrección mostraban la puerta, *con razón*. Antes no se notaba porque el producto nunca preguntaba al GPS.

Ahora «sin señal» es `POSITION_UNAVAILABLE` (code 2), explícito y determinista. **3 de 3 ejecuciones estables.**

---

## 8. Validación

**445 tests · 0 fallos · 0 errores · 1 saltado**, por lotes separados, sobre base de tests limpia.

### Nuevos

| Archivo | Tests | Qué fija |
|---|---:|---|
| `tests/e2e/test_location_gate_field_defects_browser.py` | 5 | los tres defectos de campo, con sus dos controles |
| `test_location_permission_gate.py` (+2) | 12 | la marca del 403 · la parada sin empezar se resuelve |

### Discriminantes: fallan con la versión en producción

Guardé la corrección, reconstruí el bundle desde `dev` —el !67 tal como está desplegado— y ejecuté los tests nuevos:

```text
=== CON LA VERSIÓN EN PRODUCCIÓN (!67) ===
FAILED test_la_ubicacion_del_telefono_apagada_muestra_la_puerta
FAILED test_con_jornada_abierta_la_puerta_aparece_y_solo_queda_cerrar
FAILED test_una_accion_encolada_antes_del_despliegue_no_se_pierde
3 failed, 2 passed
```

Fallan exactamente los tres de defecto, y pasan los dos controles —«sin señal no bloquea» y «conceder restaura»—, que deben pasar en las dos versiones. Con la corrección, 5/5.

### Un test corregido porque codificaba el defecto

`test_revocar_a_mitad_no_atrapa_la_jornada` afirmaba que con jornada abierta la puerta **no** aparece. Ése era el defecto 2. Ahora afirma lo que exige la instrucción: la puerta encima y `End Work` debajo.

### Lotes

| Lote | Tests | Fallos | Err | Skip |
|---|---:|---:|---:|---:|
| `test_location_permission_gate.py` | 12 | 0 | 0 | 0 |
| `test_operational_action_matrix.py` | 6 | 0 | 0 | 0 |
| `test_work_sessions.py` | 42 | 0 | 0 | 0 |
| `test_trips.py` | 66 | 0 | 0 | 0 |
| `test_activities.py` | 37 | 0 | 0 | 0 |
| `test_route_location_evidence.py` | 39 | 0 | 0 | 0 |
| `test_route_exact_correlation.py` | 14 | 0 | 0 | 0 |
| `test_route_mileage_engine.py` | 24 | 0 | 0 | 1 |
| `test_odometer.py` | 37 | 0 | 0 | 0 |
| `test_odometer_end_work.py` | 11 | 0 | 0 | 0 |
| `test_live_today.py` | 15 | 0 | 0 | 0 |
| `test_activity_explorer.py` | 17 | 0 | 0 | 0 |
| redes de cableado, superficie pública y catálogo | 63 | 0 | 0 | 0 |
| **navegador** `test_location_gate_field_defects_browser.py` (nuevo) | 5 | 0 | 0 | 0 |
| **navegador** `test_location_permission_gate_browser.py` | 6 | 0 | 0 | 0 |
| **navegador** `test_rte05_workbench_browser.py` | 24 | 0 | 0 | 0 |
| **navegador** `test_trip_and_odometer_browser.py` | 6 | 0 | 0 | 0 |
| **navegador** `test_activity_execution_browser.py` | 15 | 0 | 0 | 0 |
| **navegador** `test_rte06_bounded_queue_browser.py` | 2 | 0 | 0 | 0 |
| **navegador** `test_rte06_silent_capture_browser.py` | 2 | 0 | 0 | 0 |
| **navegador** `test_rte06_end_restoration_browser.py` | 2 | 0 | 0 | 0 |

* **Frontend** `npm run check` → typecheck **0 errores**, lint **0 errores**
* **Frontend** `npm run build:prod` → compilado
* **Migraciones** → `NOT APPLICABLE`

---

## 9. Matriz de acciones, actualizada

| Acción | Endpoint | ¿Exige permiso? | Sin permiso, a mitad |
|---|---|---|---|
| `worksession.start` | `POST /worksessions` | **sí** | bloqueada |
| `trip.plan` | `POST /trips` | **sí** | bloqueada |
| `trip.start` | `POST /trips/{}/start` | **sí** | bloqueada |
| `trip.change_plan` | `POST /trips/{}/change-plan` | **sí** | bloqueada |
| `trip.arrive` | `POST /trips/{}/arrive` | no | permitida |
| **`activity.start`** | `POST /trips/{}/activity/start` | **no** *(decisión de CER)* | **permitida** |
| `activity.complete` | `POST /trips/{}/activity/complete` | no | permitida |
| `activity.leave` | `POST /trips/{}/activity/leave` | no | permitida |
| `worksession.end` | `POST /worksessions/{}/end` | no | permitida |

La red `tests/test_operational_action_matrix.py` sigue cruzando las tres fuentes —clasificación del cliente, llamadas a `enqueueAction`, decoradores del servidor— y queda verde con la reclasificación.

---

## 10. Asuntos restantes

**Dentro del alcance: ninguno.**

**A confirmar en campo, declarado así:**

1. **La ventana de 500 ms.** Se apoya en que una denegación del sistema llega en milisegundos — es una comprobación de autorización, no una búsqueda de satélites. Es un margen de más de cincuenta veces, pero es una propiedad del dispositivo y conviene confirmarla en un Android y un iPhone reales.
2. **Safari de iOS**, donde la Permissions API puede no existir y manda el sondeo.

**Acción operativa:** desplegar. Es frontend y backend; el job ya reconstruye el bundle. Sin migración.

**Nota para los cuatro supervisores con la ubicación desactivada** (272, 271, 274, 269): con esta corrección **sí verán la puerta**, que es el comportamiento pedido. Conviene avisarles antes del despliegue.

---

## 11. Estado propuesto

```text
RTE10-A02 FIELD CORRECTION COMPLETE / READY FOR CER VALIDATION
```

---

## 12. Estimación del esfuerzo

| Tarea | Estado | Complejidad | Horas-agente |
|---|---|---|---|
| Diagnóstico: despliegue, cola, datos de campo y modelo de estados | `DONE` | diagnóstico | 2,0 |
| Defecto 1: verificación con ventana de denegación | `DONE` | UI/navegador | 1,6 |
| Defecto 2: puerta compacta y retirada de aperturas por fase | `DONE` | UI | 2,4 |
| Defecto 3: marca del servidor, cola y acciones heredadas | `DONE` | frontend + backend | 1,6 |
| Defecto 4: reclasificación de `activity.start` | `DONE` | producto | 0,6 |
| Corrección de la regresión de espera (§6) | `DONE` | diagnóstico | 0,8 |
| Tests deterministas de «sin señal» (§7), con medición | `DONE` | diagnóstico | 1,0 |
| Tests nuevos (7) y verificación contra producción | `DONE` | UI/navegador | 3,0 |
| Regresión completa (445 tests), varias pasadas | `DONE` | ejecución | 2,4 |
| Reporte | `DONE` | documentación | 0,8 |
| **Subtotal** | | | **16,2** |
| Margen (+50 %, automatización de navegador) | | | **+8,1** |
| **Total** | | | **≈ 24,3 h-agente** |

---

## 13. Siguiente paso

Desplegar y validar en campo los dos puntos de §10. **No se inicia Reports, ni RTE09, ni se reanuda RTE10-A01.**
