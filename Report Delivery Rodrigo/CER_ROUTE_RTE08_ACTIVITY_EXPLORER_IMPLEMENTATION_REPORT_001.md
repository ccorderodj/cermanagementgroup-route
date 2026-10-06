# CER Route — RTE08 · Activity Explorer
## Reporte de implementación 001

**Instrucción:** `CER_ROUTE_RTE08_ACTIVITY_EXPLORER_INSTRUCTIONS_001.md` (rev. 002)
**Rama:** `feature/rte08-activity-explorer` (desde `dev`, con RTE07 certificado)
**Fecha:** 2026-10-06

---

## 1. Resultado ejecutivo

El Activity Explorer está implementado contra la línea base V0.7, de sólo
lectura, sobre los hechos ya certificados de Work Session, Trip y Activity
Execution. **No se añadió ninguna persistencia.**

Tres hallazgos de CP1 cambiaron la forma de implementarlo, y los tres salieron
de **leer el mockup** en vez de suponer cómo debía ser:

1. **La jerarquía existe en V0.7, pero no es un árbol.** Es un desglose entre
   vistas de rango: el año agrupa por mes con una fila que dice `View month`, el
   mes por semana, la semana por día, y el día enseña las paradas. Implementarlo
   como acordeón habría sido la suposición natural y habría roto §2.4.
2. **La convención de semana la resuelve el propio mockup, así que no hubo que
   parar.** Sus grupos de mes rompen en `Sep 1–6`, `Sep 7–13`, `Sep 14–20`,
   `Sep 21–27`, y el 7, el 14 y el 21 de septiembre de 2026 son **lunes**:
   semana lunes–domingo, recortada al mes, etiquetada como rango de fechas y no
   como número ISO. FR-04 contemplaba un STOP; la evidencia estaba.
3. **El móvil de esta pantalla oculta dos filtros.** El mockup tiene un ámbito
   `.app.device-mobile` explícito que dice `.fields-inline { display: none }`,
   y en Reports los vuelve a mostrar. No es reflow accidental: es una decisión
   de V0.7 que se reprodujo.

Además, **mis propias capturas encontraron dos desviaciones mías** y un test de
navegador encontró **un defecto real del producto**. Los tres están corregidos y
documentados en §6 y §17.

---

## 2. La línea base exacta, localizada

```text
_cer_delivery/CER_ROUTE_RTE01_PACKAGE_V1_0/04_Mockup_Reference_V0_7/standalone.html
```

La función autoritativa es **`adminActivity()`**, con sus auxiliares
`activityCards()` y `groupRows(range)`. En el menú lateral
(`adminNav()`) y en el inferior móvil (`adminMobileNav()`) la entrada se llama
**`Activity`**, no «Activity Explorer».

Nota de método: el mockup no contiene la cadena «Explorer» en ninguna parte.
Buscarla no habría encontrado nada; lo que localizó la pantalla fue buscar los
términos de la jerarquía.

---

## 3. Inventario de V0.7

| Elemento | Qué hace exactamente en el mockup |
|---|---|
| **Raíz** | `top('Activity', 'Explore operational history by supervisor and period', '<button>Back to Today</button>')` |
| **Filtros** | `Supervisor` (select) + `Date` (input date) + pestañas `Day · Week · Month · Year`. Nada más |
| **Año** | `groupRows('year')`: título `2026`, pista `Grouped by month`, insignia `9 groups`, filas `January … September` |
| **Mes** | `groupRows('month')`: título `September 2026`, `Grouped by week`, filas `Sep 1–6`, `Sep 7–13`, `Sep 14–20`, `Sep 21–27` |
| **Semana** | `groupRows('week')`: título `Sep 14–20`, `Grouped by day`, filas `Mon Sep 14` … `Fri Sep 18` |
| **Día** | `summary-strip` de 4 mini-estadísticas (`miles`, `activity time`, `activities`, `estimated fuel`) + `activityCards()` |
| **Actividad** | Tarjeta: cabecera con propósito, `ref · hh:mm–hh:mm`, derecha `span · miles` sobre `activity span · trip miles`; cuerpo con `Travel`, `At destination`, `Reason`, `Outcome` y `Note` (ésta a `span 2` de 3 columnas) |
| **Detalle aparte** | **No existe.** La tarjeta *es* el detalle: no hay panel lateral ni pantalla de actividad individual |
| **Fila de grupo** | Es un `<button>` con `data-drill`; a la derecha `${r[4]} est. fuel · View ${drill}`. Ése es el mecanismo de desglose |
| **Vuelta** | Las pestañas de rango. No hay botón «atrás» dentro de la jerarquía; sí `Back to Today` |
| **Estado vacío** | El mockup **no lo define**: sus datos de demo nunca están vacíos |
| **Móvil** | Ámbito `.app.device-mobile`: filtros apilados, **campos ocultos**, resumen a 2 columnas, cuerpo de tarjeta a 2 columnas, barra inferior en vez de lateral |
| **Orden** | Cronológico ascendente en los tres niveles |
| **Periodos vacíos** | No se dibujan: la semana del mockup va de lunes a viernes porque el fin de semana no tuvo jornada |

---

## 4. Mapeo V0.7 → dominio → implementación

| V0.7 | Hecho autoritativo | Implementación |
|---|---|---|
| Agrupación por año/mes/semana/día | `WorkSession.session_date` | `GROUP BY session_date`, una consulta por periodo |
| Propósito de la tarjeta | `Trip.current_purpose` | Encabezado `h4`, con etiqueta aprobada |
| Referencia | `Trip.current_context_reference` | Línea de contexto |
| `Reason` | **ver abajo** | Etiquetas congeladas o valor del plan |
| `Outcome` | `ActivityExecution.outcome_label` | Línea `Outcome` |
| `Note` | `ActivityExecution.notes` | Línea `Note` |
| `Travel` | `Trip.started_at → Trip.arrived_at` | Calculado en pantalla |
| `At destination` | `ActivityExecution.started_at → ended_at` | Calculado en pantalla |
| `activity span` | `Trip.started_at → ActivityExecution.ended_at` | Cabecera de la tarjeta |
| `trip miles` | `TripMileage.total_meters` (sólo `CALCULATED`) | Millas oficiales |
| `activities` | Nº de bloques de ejecución | Resumen y filas de grupo |
| `activity time` | Suma de duraciones de bloques **terminados** | Resumen y filas de grupo |
| `estimated fuel` | **No existe en el dominio** | `—` por D-01 (§17) |
| Selector de supervisor | `SupervisorProfile` activos del tenant | Autorizado en el servidor |

### `Reason`, y por qué no mezcla propósito con actividad

El dominio certificado parte los contextos en dos conjuntos **disjuntos y
complementarios**:

```text
POSTARRIVAL_ACTIVITY_LIST = client_visit, recruiting, other   -> eligen al llegar
PRETRIP_STANDARD_LIST     = employee_visit, check_delivery, office -> traen valor del plan
```

Nunca los dos, nunca ninguno. Y es exactamente lo que hace V0.7: su
`arrivalFields()` sólo rinde el selector «Visit activity» cuando el propósito es
`client`; para los demás el valor viene del formulario previo. Por eso la línea
`Reason` enseña **las actividades seleccionadas** donde las hay y **el valor del
plan** donde no, mientras el propósito se queda en la cabecera. Eso mantiene
Purpose y Activity distintos (PR-04) en vez de colapsarlos.

**Un límite heredado, declarado:** el viaje guarda `current_standard_value_id`
pero **no** una copia congelada de su etiqueta, al contrario que las actividades
y el resultado. Para los tres contextos del plan, la etiqueta se lee del
catálogo. Un valor **retirado** sigue siendo legible —su clave foránea es
`RESTRICT`, no desaparece de debajo de un histórico— pero un **renombrado**
cambiaría esa etiqueta en el pasado. Es una propiedad anterior a RTE08 y
congelarla exigiría tocar el dominio de Trip, que §26 prohíbe. Se reporta, no se
arregla por iniciativa propia.

---

## 5. Compatibilidad multi-Activity

```text
V0.7                  una sola actividad por parada, en la línea `Reason`
regla certificada     un bloque de ejecución con una o varias actividades,
                      compartiendo horas, resultado y nota
adaptación exacta     la línea `Reason` enseña **todas** las etiquetas
                      seleccionadas, separadas por coma, en la MISMA tarjeta
impacto visual        ninguno estructural: una tarjeta por parada, las mismas
                      cinco líneas, el mismo orden
```

Es la adaptación mínima que §5 autoriza. **No** se fabrican ejecuciones
independientes: un test de integración comprueba que tres actividades
seleccionadas producen **una** parada y que el contador del resumen dice `1`, y
un test de navegador comprueba que las dos etiquetas aparecen en una sola
tarjeta.

---

## 6. El contrato de lectura, tal como quedó

```text
GET /api/activity-explorer?range=day|week|month|year&date=YYYY-MM-DD&supervisor_user_id=N
    -> route.activity.read, alcance de compañía por subdominio
```

Un endpoint y **un nivel por petición**. No hay tres contratos: hay uno con
cuatro profundidades. Partirlo obligaría al navegador a saber qué agrupa cada
rango, que es una regla de producto.

La respuesta trae `range`, `start`, `end`, `grouped_by`, los `supervisors`
autorizados, el `supervisor_user_id` vigente, y después `groups` **o**
`summary` + `activities` según el nivel.

**El servidor devuelve fechas; la pantalla compone los textos.** La convención
—semana lunes a domingo, recorte al mes, día de negocio— es dominio y se prueba
en integración. El formato —`Sep 14–20`, `Mon Sep 14`, `January`— es
presentación. Es la misma separación que ya usa Today / Live con sus etiquetas
de estado.

**Un defecto propio, encontrado por el test de navegador:**

```text
síntoma    Cambiar la fecha y pulsar un rango enseguida dejaba la vista en el
           nivel viejo mientras la pestaña marcaba el nuevo.
causa      PRODUCT DEFECT (`CONFIRMED`). Dos lecturas solapadas; si la primera
           contestaba después, pisaba a la segunda. Comprobar que el componente
           sigue montado no basta: hay que comprobar que la respuesta que llega
           es la que se espera.
corrección Un contador de lectura vigente (`lecturaVigente`), el mismo patrón
           que ya protege la captura de odómetro.
evidencia  Antes: el test fallaba sin espera artificial y pasaba con 1,5 s de
           pausa. Después: pasa sin pausa ninguna.
```

Se corrigió el producto en vez de añadir una espera al test, que habría
escondido el defecto en lugar de arreglarlo.

---

## 7. Semántica de la jerarquía

* **Día de negocio.** Todo agrupa por `WorkSession.session_date`, calculado una
  vez al abrir la jornada. Un test coloca un bloque de ejecución a la **1:10 AM
  del día natural siguiente** y comprueba que sigue bajo su día de negocio y que
  **no** aparece además en el día siguiente.
* **Semana.** Lunes a domingo, recortada al mes. Un test fija los grupos de
  septiembre de 2026 en `Sep 1–6` y `Sep 14–20`.
* **Grupos vacíos.** No se dibujan, como en la línea base.
* **Orden.** Cronológico ascendente; las paradas, por hora de ocurrencia y, a
  igualdad, por identificador. Un test lee dos veces y compara.

---

## 8. Fidelidad de escritorio

Validada a **1280 × 900**, contra el mockup capturado al mismo tamaño.

Raíz, jerarquía completa (`Year → Month → Week → Day → Activity` bajando por las
filas), tarjeta de parada con sus cinco líneas, filtros, estado vacío y error de
lectura: **8 tests de navegador, 8/8 PASS**.

---

## 9. Fidelidad móvil

Validada a **390 × 844**, como contrato aparte y no como reflow del escritorio.

Lo que V0.7 define para móvil en esta pantalla, reproducido: filtros apilados,
**selector de supervisor y fecha ocultos**, resumen a dos columnas, cuerpo de
tarjeta a dos columnas, sin desbordamiento horizontal.

Consecuencia que conviene decir en voz alta: **en móvil el camino al pasado es
la jerarquía**, porque el selector de fecha no está. Un test recorre
año → mes → semana → día → parada entero con interacciones táctiles y sin
depender de nada que sólo exista en escritorio.

---

## 10. Matriz de cierre visual

```text
Desktop root ....................... MATCH
Desktop hierarchy .................. MATCH
Desktop Activity presentation ...... MATCH
Desktop detail ..................... N/A  (V0.7 no tiene detalle aparte: la
                                           tarjeta es el detalle)
Desktop filters .................... MATCH

Mobile root ........................ MATCH
Mobile hierarchy ................... MATCH
Mobile Activity presentation ....... MATCH
Mobile detail ...................... N/A  (igual que en escritorio)
Mobile navigation/back ............. MATCH  (las pestañas de rango; `Back to
                                             Today` en la cabecera)
Mobile filters ..................... MATCH  (ocultos, como manda el ámbito
                                             `.app.device-mobile`)

Labels ............................. MATCH
Ordering ........................... MATCH
Expanded/collapsed behavior ........ MATCH  (desglose por fila + pestañas)
Empty state ........................ APPROVED DELTA  (ver abajo)
Multi-Activity adaptation .......... APPROVED DELTA  (§5)
```

### Los dos `APPROVED DELTA`, y dos más que no son de estructura

**D-A · Estado vacío**

```text
V0.7         no lo define: sus datos de demo nunca están vacíos
Implementado "No recorded activity on this day." / "...in this period.",
             con la insignia `0 groups`
Razón        FR-08 exige un estado vacío veraz y la línea base no ofrece uno
Regla        FR-08: no se fabrican filas; un fallo de lectura no es un periodo
             vacío
Aprobación CER requerida   NO  (la instrucción pide el estado; el texto sigue
                                el patrón del repositorio)
```

**D-B · Multi-Activity** — descrito en §5. `Aprobación CER requerida: NO`
(§5 la autoriza de forma explícita).

**D-C · `estimated fuel`**

```text
V0.7         $6.49 en el resumen del día y `$47.23 est. fuel` en cada fila
Implementado `—` en los dos sitios
Razón        No existe precio por galón en el dominio
Regla        D-01 de CER, decidida en RTE07: se conserva el hueco y no se
             inventa un precio
Aprobación CER requerida   NO  (ya decidido; §17 da prioridad a la decisión
                                certificada posterior en el conflicto exacto)
```

**D-D · Millaje pendiente**

```text
V0.7         siempre un número de millas
Implementado el número más `+ pending` cuando algún viaje del periodo todavía
             no tiene millaje calculado
Razón        Presentar un viaje sin calcular como `0.0 mi` lo haría parecer
             final
Regla        Mismo tratamiento certificado en RTE07 para `mileage_pending`
Aprobación CER requerida   NO  (precedente certificado; es veracidad, no
                                un elemento nuevo)
```

### Dos desviaciones mías, encontradas comparando capturas y **corregidas**

No se marcan como MATCH por equivalencia funcional: se arreglaron.

| Desviación | Cómo apareció | Corrección |
|---|---|---|
| Añadí un título de día (`Fri Sep 18`) sobre el resumen | La captura de V0.7 pasa de la barra de filtros a las mini-estadísticas sin título | Retirado. §17 prohíbe añadidos visuales, y la fecha ya está en su selector |
| La línea `Note` ocupaba las tres columnas y caía a una tercera fila | V0.7 la pone a `span 2` de 3, junto a `Outcome` | `col-span-2`. La jerarquía visual vuelve a ser la aprobada |

Y una tercera, en la **evidencia** y no en el producto: la primera captura de
referencia móvil salió con la barra lateral de escritorio visible, porque le
puse la clase `device-mobile` a mano en vez de pulsar el conmutador del propio
mockup. Una captura de referencia equivocada invalida la comparación entera, así
que se corrigió el método de captura.

---

## 11. Roles, autorización y aislamiento

* **`route.activity.read`**, declarada en `app/core/rbac/catalog.py` con este
  checkpoint —antes estaba reservada con un comentario a propósito: el catálogo
  rechaza una capacidad que ningún endpoint exija— y concedida al rol
  **`route_admin`**, no al de supervisor: un supervisor ve sus paradas en su
  móvil, no la historia de los demás.
* Exigida en el **servidor** por el endpoint y por la ruta de página, con la
  misma capacidad en los dos sitios: pedir una distinta llevaría a una pantalla
  que después devuelve 403.
* Un supervisor que escriba la URL **no entra**: test de navegador.
* El supervisor de otro tenant devuelve **404 y no 403**: confirmar que existe
  ya sería decir algo de otra compañía.
* Las opciones del selector salen del servidor. El frontend no filtra: lo que no
  se devuelve, no existe para la pantalla.
* **Sin coordenadas, sin mapa, sin historial de ubicación.** No se añadió ningún
  campo de localización.
* RTE08 no escribe nada, así que no se introdujo lógica de auditoría de
  escritura.

---

## 12. Exactitud histórica

| Afirmación | Evidencia |
|---|---|
| El día de negocio manda sobre el día UTC | bloque a la 1:10 AM que no se mueve de día |
| Varias actividades = un hecho | 3 seleccionadas → 1 parada, contador `1` |
| Propósito ≠ actividad | `client_visit` con etiquetas y sin valor de plan; `office` al revés |
| Un valor retirado sigue legible | `is_active = false` y la parada se sigue leyendo |
| Un bloque en curso no duró cero | `activity_seconds = 0` **con** `has_open_activity = true` |
| Cada supervisor con su historia | dos supervisores el mismo día, sin cruce de vehículo ni de referencia |
| Orden determinista | dos lecturas iguales |

---

## 13. Rendimiento y lecturas acotadas

Medido sobre el registro del middleware de rendimiento —observación, no
instrumentación del motor, porque instrumentarlo rompió la suite en un
checkpoint anterior:

```text
día con 1 parada  y  1 etiqueta   -> query_count=8
día con 5 paradas y 15 etiquetas  -> query_count=8
```

El coste **no crece con las filas**. Las actividades seleccionadas se piden
todas de una vez para los bloques del día, no bloque a bloque.

* Abrir la página pide **un** nivel, no la historia del tenant.
* Bajar por una rama no trae las hermanas.
* La agregación por día cubre el periodo entero en una consulta; los grupos
  superiores se componen sumando esos días.
* **Sin paginación visible**: §15 la prohíbe salvo que V0.7 la tenga, y no la
  tiene.

---

## 14. Casos límite (§16)

| # | Caso | Estado |
|---|---|---|
| 1 | Sin actividades históricas | **tested** (vacío en día y en año) |
| 2 | Una actividad en un día | **tested** |
| 3 | Varias actividades en un día | **tested** (orden determinista, 3 paradas) |
| 4 | Varios días en una semana | **tested** |
| 5 | Varias semanas en un mes | **tested** |
| 6 | Varios meses en un año | **tested** |
| 7 | Varios años | cubierto por el anclaje de periodo; **no** hay test propio |
| 8 | Jornada que cruza medianoche | **tested** |
| 9 | Un bloque con varias actividades | **tested** |
| 10 | Horas/resultado/nota compartidos | **tested** (una tarjeta, un contador) |
| 11 | Valor retirado | **tested** |
| 12 | Distintos supervisores en el periodo | **tested** |
| 13 | Actividad de otro tenant | **tested** (404) |
| 14 | Rama vacía tras el alcance | **tested** (periodo sin registros) |
| 15 | Fallo temporal de lectura | **tested** (navegador) |
| 16 | Texto largo de nota/referencia | soportado por el dominio (`Text`); **no** hay test propio |
| 17 | Jerarquía completa en móvil | **tested** |
| 18 | Jerarquía completa en escritorio | **tested** |
| 19 | Orden determinista | **tested** |

Los casos **7** y **16** no tienen test propio y se declaran así en vez de
contarlos como verdes. Ninguno de los dos añade una regla nueva: el 7 es el
mismo anclaje de periodo con otro año, y el 16 es una columna `Text` sin límite
de producto.

---

## 15. Tests y regresión

| Lote | Tests | Resultado | Exit | Tiempo |
|---|---:|---|---:|---|
| `tests/integration/test_activity_explorer.py` (nuevo) | 17 | **17 PASS** | 0 | 35 s |
| `tests/e2e/test_rte08_activity_explorer_browser.py` (nuevo) | 8 | **8 PASS** | 0 | 103 s |
| `tests/e2e/test_rte08_activity_explorer_screenshots.py` (nuevo) | 1 | **1 PASS**, 10 imágenes | 0 | 25 s |
| RTE07 completo (integración + navegador + frescura + capturas) | 25 | **25 PASS** | 0 | 241 s |
| Dominio: jornadas, viajes, actividades, motor de millaje, reproceso | 174 | **173 PASS, 1 SKIP** | 0 | 181 s |
| Redes: página, navegación, catálogo, superficie pública | 63 | **63 PASS** | 0 | 5 s |
| `npm run check` (tsc + eslint) | — | **0 errores, 0 avisos** | 0 | — |
| `npm run build:prod` | — | **compilado** | 0 | — |
| `import app.main` | — | **OK** | 0 | — |

El `SKIP` es anterior y declarado:
`test_route_mileage_engine.py:1183 — sin ROUTE_ROUTING_URL no hay motor real que
medir (V-3)`. No se convierte en PASS.

**El bundle se reconstruyó antes de cada ejecución de navegador.** No está en
Git y el arnés no lo compila solo; un test de navegador contra un bundle viejo
valida código que no se entrega.

---

## 16. Esperado → Implementado → Evidencia → Hueco

| AC | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | Línea base V0.7 exacta localizada y usada | **VALIDATED** | §2, §3 |
| 2 | CP1 completado antes de implementar | **VALIDATED** | §3, §4 |
| 3 | Jerarquía `Year → Month → Week → Day → Activity` | **VALIDATED** | test de recorrido completo |
| 4 | Escritorio coincide con V0.7 | **VALIDATED** | §8, §10, capturas |
| 5 | Móvil coincide con V0.7 | **VALIDATED** | §9, §10, capturas |
| 6 | Semántica de día de negocio | **VALIDATED** | §7 |
| 7 | Jornada que cruza medianoche | **VALIDATED** | test propio |
| 8 | Datos del dominio certificado | **VALIDATED** | §4; sin persistencia nueva |
| 9 | Purpose y Activity distintos | **VALIDATED** | §4, test propio |
| 10 | Varias actividades, un bloque, todas visibles | **VALIDATED** | §5 |
| 11 | Horas/resultado/nota no duplicados | **VALIDATED** | §5 |
| 12 | Valores retirados legibles | **VALIDATED** | test propio |
| 13 | Sólo los filtros de V0.7 | **VALIDATED** | §3, test de raíz |
| 14 | `route.activity.read` en el servidor | **VALIDATED** | §11 |
| 15 | Supervisor sin acceso al explorador | **VALIDATED** | test de API y de navegador |
| 16 | Sin lectura entre tenants | **VALIDATED** | 404 |
| 17 | Sin ubicación ni mapa | **VALIDATED** | §11 |
| 18 | Sin persistencia duplicada | **VALIDATED** | modelo de lectura puro |
| 19 | Lecturas acotadas | **VALIDATED** | §13 |
| 20 | Vacío y error veraces | **VALIDATED** | §10 D-A, test de navegador |
| 21 | Sin desbordamiento móvil | **VALIDATED** | aserción en los dos tests móviles |
| 22 | Jornada/viaje/actividad sin cambios | **VALIDATED** | 173 PASS |
| 23 | RTE07 sin cambios | **VALIDATED** | 25 PASS |
| 24 | Typecheck/lint/build y regresión verdes | **VALIDATED** | §15 |
| 25 | Matriz de cierre sin `DEVIATION` sin resolver | **VALIDATED** | §10 |
| 26 | Sin `PARTIAL`/`GAP`/`BLOCKED`/decisión pendiente | **VALIDATED** | §17 |

**Hueco dentro del alcance de RTE08: ninguno.**

---

## 17. Desviaciones

Las cuatro `APPROVED DELTA` y las dos desviaciones propias corregidas están en
**§10**, no enterradas aquí.

Lo que **no** se hizo, por estar fuera de alcance: Reports, exportación a Excel,
gráficas, tarjetas KPI, mapa, búsqueda, controles de rango de fechas, filtros
que V0.7 no tiene, paginación visible, jerarquía organizativa, corrección de
registros, y cualquier cambio a Today / Live, odómetro/OCR o al dominio de
jornada, viaje y actividad.

**Límite heredado declarado**: la etiqueta del valor de propósito del viaje no
está congelada (§4). Pre-existente, reportado, no corregido por iniciativa
propia.

---

## 18. Lista de validación para CER

1. Entrar a **Activity** desde el menú lateral como administrador de Route.
2. Comprobar raíz: título, subtítulo, `Back to Today`, los dos filtros y las
   cuatro pestañas.
3. Recorrer `Year → Month → Week → Day` pulsando las filas, y comprobar que el
   pie de cada fila dice a dónde lleva.
4. Abrir un día con paradas y revisar la tarjeta: `Travel`, `At destination`,
   `Reason`, `Outcome`, `Note`.
5. Comprobar que una parada con **varias** actividades sale en **una** tarjeta.
6. Repetir del 2 al 5 en un teléfono, donde los filtros no aparecen y el camino
   es la jerarquía.
7. Entrar con una cuenta de supervisor escribiendo la URL: debe rechazarse.
8. Elegir un periodo sin registros y comprobar que lo dice.

**Acción operativa — ésta sí hace falta:**

```bash
uv run python -m app.db.scripts.bootstrap
```

La capacidad **`route.activity.read` es nueva** y hay que sembrarla en cada
entorno. Sin ese paso, el menú no enseña Activity y la página responde 403
aunque el código esté desplegado. No lo hace el despliegue por sí solo.

Sin migraciones: no hay cambio de esquema.

---

## 19. Estado propuesto

```text
RTE08 IMPLEMENTATION COMPLETE / READY FOR CER VALIDATION
```

Fidelidad demostrada por separado en escritorio y móvil, con capturas del
mockup y de producción al mismo tamaño; jerarquía y datos veraces; semántica
multi-Activity preservada; autorización y aislamiento verdes; lecturas
acotadas y medidas; regresión verde; matriz de cierre sin desviación sin
resolver.

No se declara `RTE08 CLOSED`: la certificación final es de CER.

---

## 20. Estimación del esfuerzo

Volumen real (`git diff --numstat`, sin contar el documento de instrucciones):

| Componente | Líneas |
|---|---|
| Backend: `activityexplorer/` (dao, router, schemas) | 767 |
| Frontend: entidad, 4 componentes y página | 740 |
| Cableado: catálogo, navegación, ruta, plantilla, mapa | 55 |
| Tests: integración, navegador y capturas | 1 317 |
| **Total** | **≈ 2 879 / −11** |

| Tarea | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| CP1: inventario de V0.7 y mapeo al dominio | `DONE` | lectura y medición | análisis | 1,5 |
| Contrato de lectura y DAO | `DONE` | ~767 LoC | backend/dominio | 4,5 |
| Entidad, componentes y página | `DONE` | ~740 LoC | UI | 12,0 |
| Cableado y capacidad nueva | `DONE` | ~55 LoC | backend | 0,4 |
| Tests de integración | `DONE` | ~664 LoC | backend | 4,0 |
| Tests de navegador y capturas lado a lado | `DONE` | ~653 LoC | UI/navegador/E2E | 11,0 |
| Corrección del defecto de carrera | `DONE` | ~10 LoC | UI | 0,4 |
| Corrección de las dos desviaciones visuales | `DONE` | ~15 LoC | UI | 0,5 |
| Regresión por lotes + build + typecheck | `DONE` | 288 tests | ejecución | 1,2 |
| Reporte 001 | `DONE` | — | documentación | 0,8 |
| **Subtotal ejecutado** | | | | **36,3** |
| Margen de riesgo (+50%, automatización de navegador) | | | | **+18,2** |
| **Total del checkpoint** | | | | **≈ 54,5 h-agente** |

Coeficientes de `_cer_delivery/estimacion_de_tiempo_y_esfuerzo.md`:
backend/dominio 150–200 LoC/h, UI/navegador/E2E 50–70 LoC/h. El margen aplicado
es el de automatización de navegador, que es donde está el grueso.

---

## 21. Trabajo restante y siguiente paso

**Restante dentro de RTE08: nada.**

**Acción operativa:** sembrar `route.activity.read` con `bootstrap` en cada
entorno (§18). El trabajo local **no** lo hace.

**Siguiente paso, sin empezarlo:** validación y certificación de CER sobre §18.
No se inicia RTE09, no se reanuda RTE10-A01 y no se promueve trabajo no
relacionado.
