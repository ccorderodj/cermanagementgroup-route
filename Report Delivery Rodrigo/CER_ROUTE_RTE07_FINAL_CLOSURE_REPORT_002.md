# CER Route — RTE07 · Cierre final de Today / Live
## Reporte 002

**Instrucción:** `CER_ROUTE_RTE07_FINAL_CLOSURE_INSTRUCTIONS_002.md`
**Rama:** `feature/rte07-final-closure` (desde `dev`, que ya contiene RTE07)
**Fecha:** 2026-10-06
**No sustituye al reporte 001**, lo completa.

---

## 1. Resultado del cierre

Los cinco escenarios que el reporte 001 dejó como «implementados pero sin
evidencia propia» están ahora **ejecutados y verdes**, y la decisión D-01 de CER
queda registrada en el código y comprobada por un test.

No hizo falta corregir ningún comportamiento del producto: los cuatro
mecanismos de frescura y recuperación funcionaban. Lo que faltaba era medirlos,
y medirlos obligó a resolver dos cosas que conviene que CER conozca:

1. **El único mecanismo que esconde una pestaña en este arnés** hubo que
   encontrarlo midiendo: de cuatro candidatos, tres no funcionan y uno de ellos
   está **retirado del protocolo** de Chrome (§3).
2. **Los tests se verificaron rompiendo el producto a propósito.** Una aserción
   del tipo «cero peticiones mientras está oculta» pasa igual de verde si el
   contador nunca estuvo conectado, así que no basta con que pase: hay que ver
   que **detecta**. Se mutó el componente, se reconstruyó el bundle y los dos
   tests fallaron como debían; después se revirtió (§3.5).

Sin esa comprobación, FC-03 y FC-04 habrían sido dos verdes sin contenido — y
en este mismo proyecto ya ocurrió antes.

---

## 2. Decisiones de CER aplicadas

### D-01 — Combustible estimado: **registrada**

El hueco de V0.7 se conserva y enseña el valor neutro `—`. No se inventó
ningún precio por galón, no se usó un valor por defecto, no se construyó
`Fuel Reference` dentro de RTE07 y no se tocó la semántica de millaje.

Lo que cambió es **el estado de la cuestión, no el píxel**: el comentario del
componente la describía como «desviación listada en el reporte de entrega», y
ahora dice que CER la revisó y aprobó este tratamiento, con el fondo de la
decisión escrito —un coste estimado a partir de un número fabricado se lee como
un hecho y nadie sabría que no lo es.

Y se añadió lo que faltaba para que esto sea evidencia y no una afirmación:

| Presentación | Aserción | Resultado |
|---|---|---|
| Escritorio (1280×900) | el `<b>` de la mini-estadística `estimated fuel` tiene el texto `—` | **PASS** |
| Móvil (390×844), detalle a pantalla completa | la misma, en la otra presentación aprobada | **PASS** |

Se localiza **el valor** y no la etiqueta a propósito: comprobar que el texto
«estimated fuel» existe dejaría pasar un número inventado debajo de él.

Para RTE07, el estado correcto es el que pide la instrucción:
`hueco conservado / sin valor autorizado / "—" neutro`. **Deja de ser un hueco
pendiente.**

### D-02 — Frescura: **aprobada y ahora medida**

No se rediseñó nada. El sondeo sigue siendo de 30 s con pausa en segundo plano
y relectura inmediata al volver, sin WebSocket. Lo que se añadió es la
evidencia de §3 y §4.

---

## 3. Validación de frescura

### FC-01 — El refresco automático refleja un cambio real · **PASS**

```
setup    Supervisor con perfil, vehículo y jornada abierta.
         Today / Live cargado como route_admin; la columna Status dice "Working".
         Se marca window.__sinRecarga = true.
acción   Con la página abierta y sin tocarla, el supervisor pasa a On Route por
         el camino real del producto: odómetro de inicio resuelto, viaje creado
         y arrancado (las guardas de RTE04, no un atajo).
observado La fila pasó sola a "On Route" dentro del turno de refresco.
aserción  celda Status == "On Route" (espera 45 s), "Working" ausente,
          y window.__sinRecarga sigue siendo true -> no hubo recarga.
PASS      51 s de ejecución.
```

La marca en `window` es lo que distingue «se refrescó» de «se recargó»: una
navegación la destruiría. Se esperan los **30 s reales**; acortar el intervalo
del producto para que el test corriera antes es lo que §7 prohíbe.

### FC-03 — Con la pestaña oculta no se sigue trabajando · **PASS**

```
setup    Today / Live cargado con datos reales. Se engancha un contador a
         page.on("request") filtrando /api/live/today.
acción   La pestaña pasa a oculta; se verifica document.visibilityState ==
         "hidden"; se espera 35 s (un turno completo y algo más).
observado Ninguna petición durante la ventana oculta.
aserción  lecturas == []  ... y después el **control positivo**: al volver al
          frente el contador registra, lo que demuestra que el cero significaba
          algo.
PASS      53 s de ejecución.
```

**Cómo se esconde la pestaña, medido y no supuesto.** Un navegador sin ventana
no tiene pestaña que pasar a segundo plano. Se probaron cuatro mecanismos sobre
este mismo arnés (Edge headless por CDP):

| Mecanismo | Resultado medido |
|---|---|
| Abrir una segunda pestaña en el contexto | la primera sigue `visible` |
| CDP `Page.setWebLifecycleState: frozen` | sigue `visible`, sin evento |
| CDP `Emulation.setPageVisibilityOverride` | **retirado del protocolo** (`wasn't found`) |
| Redefinir el getter + despachar `visibilitychange` | `hidden`, y el oyente corre |

Se usa el cuarto porque es el único disponible. Lo que se simula es **la señal
del navegador**, no el producto: el evento es real, lo recibe el oyente que
registra la página, ese oyente lee el `document.visibilityState` real y ejecuta
su `clearInterval` y su `setInterval` de verdad. Ninguna parte del componente
está sustituida, que es lo que FC-03 exige al decir «no una aserción simulada
desconectada del ciclo de vida de la página».

### FC-04 — Al volver al frente se relee de inmediato · **PASS**

```
setup    Today / Live cargado; estado "Working".
acción   La pestaña se oculta. **Mientras está oculta**, el supervisor pasa a
         On Route por API. La pestaña vuelve a visible.
observado Oculta, la pantalla seguía enseñando "Working" (correcto: no ha podido
         observar nada). Al volver, pasó a "On Route" sin esperar el turno.
aserción  celda Status == "On Route" con espera de **10 s**, deliberadamente muy
          por debajo de los 30 s del intervalo: con 30 s la aserción no
          distinguiría «releyó al volver» de «le tocaba el turno».
PASS
```

### 3.5 — Por qué estos dos verdes se pueden creer

Una aserción de «cero peticiones» y otra de «aparece el estado nuevo» pasan
igual de verdes si el test está mal enganchado. Así que se comprobó que
**detectan**:

```
mutación  en RouteTodayLivePage.tsx, el manejador de visibilidad pasa a ser
          sólo `arrancar()`: ni para al ocultarse ni relee al volver.
bundle    reconstruido (npm run build:prod) — el navegador ejecuta el bundle,
          no el .tsx
resultado FC-03 FALLÓ: "la pestaña oculta siguió leyendo 1 veces"
          FC-04 FALLÓ: "Locator expected to have count '1' ... resolved to 0"
reversión git checkout del componente + bundle reconstruido -> los dos verdes
```

Los dos tests fallan cuando el comportamiento se rompe y pasan cuando está
bien. Eso es lo que convierte el verde en evidencia.

---

## 4. Validación de la recuperación ante error

### FC-02 — Un fallo de relectura conserva lo último cierto · **PASS**

```
setup    Today / Live cargado con datos reales: fila "Working", lista con
         cabecera y filas, resumen poblado. Se cuentan las filas.
acción   Se interceptan las peticiones a /api/live/today y se responden **500**.
         Se espera el turno de refresco.
observado Apareció el aviso recuperable de la línea base y la pantalla conservó
         todo lo que ya sabía.
aserción  presente: "Could not refresh just now. Showing the last known state."
          conservado: celda Status == "Working", nº de filas idéntico,
                      encabezado "Supervisors" presente
          ausente:   "Not started" (0), lista vacía (0 filas: no),
                     pantalla de error total "Today / Live could not be read" (0)
PASS
recuperación Se retira la intercepción y, **en el turno siguiente y sin
          intervención**, el aviso desaparece y el estado real vuelve.
PASS
```

Las aserciones negativas son el punto: un error de red no es «el supervisor no
está trabajando». Si una lectura fallida se dibujara como `Not started` o como
`0 miles`, quien mira el panel decidiría a quién llamar sobre un hecho que
nadie ha observado.

No se rediseñó la experiencia de error: el test no expuso ningún defecto.

---

## 5. Consistencia con varios supervisores

### FC-05 — Cinco supervisores, cinco estados, una sola lectura · **PASS**

Cierra el caso límite 17 del reporte 001. Nivel de integración, como §5
permite: lo que se defiende es el modelo de lectura, y un navegador no añadiría
evidencia de producto aquí.

```
setup    Cinco supervisores, cada uno con su propio vehículo, en la misma
         compañía:
           supervisor   -> viaje llegado + actividad en curso
           route_admin  -> viaje en tránsito
           manager      -> jornada abierta y cerrada
           viewer       -> jornada abierta sin viajes
           owner        -> perfil sin jornada
acción   Una sola lectura de GET /api/live/today como route_admin.
observado Cada fila con su estado, y los cinco distintos.
aserción  estados   == {activity, route, ended, working, not_started}
          distintos == 5  (si el modelo colapsara dos, el mapa anterior podría
                           cuadrar por casualidad; esto lo cierra)
          sin cruce : vehicle_label distinto entre las dos filas activas,
                      activity_reference "Acme" vs "Globex" en su dueño,
                      activities_today 1 vs 0,
                      la fila sin empezar tiene since=None y activity_label=None
          resumen   : supervisors_total == len(lista) == 5, on_route == 1,
                      in_activity == 1, supervisors_working == 3
          millaje   : total_miles == suma de los official_miles de las filas
PASS      13 s de ejecución.
```

**Un detalle de preparación que conviene declarar.** Sólo los roles
`supervisor` y `route_admin` traen `route.worksession.execute` en los roles por
defecto, y este caso necesita cuatro jornadas simultáneas. Los dos usuarios
extra se promueven al rol de supervisor con `PUT /api/users/{id}` —la pantalla
real de administración, con su `users.update` y su guarda de roles
asignables—, no concediendo la capacidad por SQL. Inventarla por detrás habría
probado un estado que el producto no puede alcanzar.

El riesgo que este test cubre es el propio de un modelo de lectura con seis
consultas fijas: una unión mal escrita no falla, **mezcla**. Y un panel que
atribuye la actividad de uno al vehículo de otro se cree durante meses.

---

## 6. Cambios de producto

**Ninguno funcional.** Los cuatro comportamientos de frescura y recuperación ya
estaban bien; ningún test expuso un defecto del producto.

| Archivo | Cambio | Naturaleza |
|---|---|---|
| `app/components/react/features/RouteLive/ui/LiveSupervisorDetail.tsx` | el comentario del combustible estimado pasa de «desviación abierta» a «D-01 aprobada», con el fondo de la decisión | documentación en el código; **sin cambio de render** |

Nada de maquetación, terminología, columnas, tarjetas, estructura del panel,
semántica de millas, reglas de jornada/viaje/actividad, RBAC, jerarquía,
ubicación, odómetro ni dominios vecinos.

### Un defecto encontrado, y era del test

```
síntoma   La primera versión de FC-01 falló: el localizador de "Working"
          resolvía 2 elementos.
causa     TEST DEFECT (`CONFIRMED`). El escritorio enseña el estado **dos
          veces** —en la fila de la tabla y en el panel lateral del supervisor
          seleccionado—, que es la línea base V0.7 funcionando como debe.
          Buscar el texto suelto encontraba los dos.
corrección Las aserciones de estado pasan por la celda de la columna `Status`
          (`role=cell`), que además es lo que V0.7 llama esa columna.
antes/después  fallo "Actual value: 2" -> 1 passed en 51 s.
regresión  Ningún código de producto se tocó por esto.
```

Se clasificó antes de cambiar nada, como pide §7. Si se hubiera «arreglado»
quitando el estado del panel lateral, el test habría pasado destruyendo
fidelidad V0.7.

---

## 7. Regresión

| Lote | Tests | Resultado | Exit | Tiempo |
|---|---:|---|---:|---|
| `tests/integration/test_live_today.py` (14 + FC-05) | 15 | **15 PASS** | 0 | 29 s |
| Navegador RTE07: estructura (5) + capturas (1) + frescura (4) | 10 | **10 PASS** | 0 | 245 s |
| Dominio: jornadas, viajes, actividades, motor de millaje, reproceso | 174 | **173 PASS, 1 SKIP** | 0 | 184 s |
| Redes: página, navegación, catálogo, superficie pública | 62 | **62 PASS** | 0 | 4 s |
| `npm run check` (tsc + eslint) | — | **0 errores, 0 avisos** | 0 | — |
| `npm run build:prod` | — | **compilado** | 0 | 52 s |

El `SKIP` es anterior y declarado:
`test_route_mileage_engine.py:1183 — sin ROUTE_ROUTING_URL no hay motor real que
medir (V-3)`. No se convierte en PASS.

**El bundle se reconstruyó antes de la regresión de navegador final**, y es una
precaución con historia: los tests de navegador ejecutan
`app/static/javascript/main.js`, que no está en Git y que el arnés no compila
por sí solo. Un test de navegador contra un bundle viejo valida código que no es
el que se entrega — ya pasó en este proyecto.

---

## 8. Esperado → Implementado → Evidencia → Hueco

Los dos primeros son los que el reporte 001 dejó en `IMPLEMENTED`.

| Reporte 001 | Criterio | Antes | Ahora | Evidencia |
|---|---|---|---|---|
| AC-14 | Refresco automático dentro de la ventana Live | `IMPLEMENTED` | **VALIDATED** | FC-01 §3 + mutación §3.5 |
| AC-15 | Un fallo de lectura no es un estado de negocio falso | `IMPLEMENTED` | **VALIDATED** | FC-02 §4 |
| AC-23 | Sin `PARTIAL` / `GAP` / `BLOCKED` en alcance | «ver §14» | **VALIDATED** | D-01 registrada §2 |
| Caso 12 | Los datos cambian con la página abierta | sin evidencia | **VALIDATED** | FC-01 |
| Caso 13 | Fallo de lectura temporal | sin evidencia | **VALIDATED** | FC-02 |
| Caso 16 | Pestaña oculta y vuelta | sin evidencia | **VALIDATED** | FC-03 + FC-04 |
| Caso 17 | Varios supervisores cambiando a la vez | sin evidencia | **VALIDATED** | FC-05 §5 |

Y los criterios de esta instrucción:

| AC | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | D-01 registrada: el hueco queda y enseña `—` | **VALIDATED** | §2, dos aserciones de navegador |
| 2 | No se inventó precio ni función de combustible | **VALIDATED** | §6: sólo un comentario cambió |
| 3 | FC-01 ejecutado y verde | **VALIDATED** | §3 |
| 4 | FC-02 ejecutado y verde | **VALIDATED** | §4 |
| 5 | FC-03 ejecutado y verde | **VALIDATED** | §3 + control positivo |
| 6 | FC-04 ejecutado y verde | **VALIDATED** | §3 |
| 7 | FC-05 ejecutado y verde | **VALIDATED** | §5 |
| 8 | Escritorio sin cambios | **VALIDATED** | 5/5 estructura, bundle nuevo |
| 9 | Móvil sin cambios | **VALIDATED** | ídem, incluido el detalle completo |
| 10 | Fidelidad visual V0.7 sin cambios | **VALIDATED** | sin cambio de render (§6); capturas de 001 siguen válidas |
| 11 | Autorización y aislamiento de tenant verdes | **VALIDATED** | 15/15 incluye capacidad y cruce de tenant |
| 12 | Semántica de Millas Oficiales verde | **VALIDATED** | 15/15 + agregación en FC-05 |
| 13 | Regresión de jornada/viaje/actividad verde | **VALIDATED** | 173 PASS / 1 SKIP declarado |
| 14 | Typecheck / lint / build verdes | **VALIDATED** | §7 |
| 15 | Sin nuevos `PARTIAL` / `GAP` / `BLOCKED` / `DECISION REQUIRED` | **VALIDATED** | §9 |

**Hueco: ninguno dentro del alcance de RTE07.**

---

## 9. Asuntos restantes

**Dentro de RTE07: ninguno.** No queda `PARTIAL`, `GAP`, `BLOCKED` ni decisión
pendiente.

**Fuera de alcance, declarado (§10 de la instrucción).** La fragilidad del arnés
asíncrono que reportó 001: **no se reprodujo** en este delta. Todas las suites
de RTE07 se ejecutaron verdes por la agrupación soportada del repositorio, y una
combinación deliberada de `test_live_today` con dos módulos no relacionados dio
**94 PASS**. No se re-verificó sobre la suite completa, porque §10 pide
explícitamente no convertir este cierre en una refactorización del arnés. Queda
como deuda técnica preexistente, y no esconde ninguna regresión de producto: lo
que se mide aquí está medido.

**Lo que `Fuel Reference` sigue necesitando, cuando CER lo decida**: una fuente
autorizada de precio por galón. El hueco de la interfaz ya está preparado y la
capacidad está reservada en el catálogo como `route.fuelreference.manage`. No es
trabajo de RTE07.

**Acción operativa: ninguna.** Sin migración, sin semilla, sin variable de
entorno nueva, sin cambio de despliegue. El único artefacto a regenerar en el
despliegue es el bundle, que ya forma parte del proceso normal.

---

## 10. Estado propuesto

```text
RTE07 IMPLEMENTATION COMPLETE / READY FOR CER FINAL CERTIFICATION
```

Los quince criterios de aceptación están verdes con evidencia ejecutada, los
cinco escenarios de frescura y consistencia están medidos, dos de ellos
verificados por mutación, y la decisión D-01 está registrada y comprobada.

No se declara `RTE07 CLOSED`: la certificación final es de CER.

---

## 11. Estimación del esfuerzo

Volumen real de este delta:

| Componente | Líneas |
|---|---|
| `tests/e2e/test_rte07_today_live_freshness_browser.py` (nuevo) | 380 |
| `tests/integration/test_live_today.py` (FC-05) | +143 |
| `tests/e2e/test_rte07_today_live_browser.py` (D-01) | +16 |
| `LiveSupervisorDetail.tsx` (comentario) | +10 / −5 |
| **Total** | **≈ 549 / −5** |

| Tarea | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Investigar el mecanismo de visibilidad (4 candidatos medidos) | `DONE` | sonda | navegador | 0,5 |
| FC-01 a FC-04 (navegador, esperas reales) | `DONE` | ~380 LoC | UI/navegador/E2E | 1,5 |
| Verificación por mutación (2 builds + 2 ejecuciones) | `DONE` | — | navegador | 0,6 |
| FC-05 (integración, cinco estados simultáneos) | `DONE` | ~143 LoC | backend/dominio | 0,8 |
| D-01: registro y aserciones de valor neutro | `DONE` | ~26 LoC | UI | 0,3 |
| Corrección del defecto de test (celda vs texto) | `DONE` | — | — | 0,2 |
| Regresión por lotes + build + typecheck | `DONE` | 261 tests | ejecución | 0,9 |
| Reporte 002 | `DONE` | — | documentación | 0,5 |
| **Subtotal ejecutado** | | | | **5,3** |
| Margen de riesgo (+50%, automatización de navegador) | | | | **+2,7** |
| **Total del delta** | | | | **≈ 8,0 h-agente** |

Coeficientes de `_cer_delivery/estimacion_de_tiempo_y_esfuerzo.md`:
UI/navegador/E2E 50–70 LoC/h, backend/dominio 150–200 LoC/h. El margen aplicado
es el de automatización de navegador, que es donde está el grueso del trabajo.

**Pendiente de CER, no estimable aquí**: la certificación final.

---

## 12. Siguiente paso

Certificación de CER sobre esta evidencia. **No se inicia RTE08, no se reanuda
RTE10-A01 y no se promueve trabajo no relacionado.**
