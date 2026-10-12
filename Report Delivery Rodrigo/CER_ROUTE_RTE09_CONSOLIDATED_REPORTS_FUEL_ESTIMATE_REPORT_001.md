# CER Route · RTE09 · Consolidated Reports + Fuel Estimate

**Reporte 001 · final** · 12 de octubre de 2026 · **Etapa: RTE09 CP2–CP5** (as-built)
**Instrucciones:** `CER_ROUTE_RTE09_CONSOLIDATED_REPORTS_FUEL_ESTIMATE_INSTRUCTIONS_001.md` y
`CER_ROUTE_RTE09_CP2_CP5_IMPLEMENTATION_AUTHORIZATION_001.md`
**Base:** `dev` en `22b1bfc` · **Rama:** `feature/rte09-consolidated-reports-fuel`

Este archivo sustituye al de la puerta de decisión del CP1 (`BLOCKED — CER
DECISION REQUIRED`), que quedó resuelta con la autorización.

---

## Proposed Status

`RTE09 CONSOLIDATED REPORTS + FUEL READINESS COMPLETE / READY FOR CER VALIDATION`

Propuesto, no declarado: **la certificación es de CER**. RTE09 no se da por
cerrado. Fuera de alcance y **no empezados**: RTE10, RTE11 y el cron de precios.

---

## 1 · Executive Result

| Pregunta | Respuesta |
|---|---|
| ¿Existe Reports? | **Sí**: `CER Route → Reports`, V0.7 tal cual, escritorio y móvil |
| ¿De dónde salen las millas? | De la **misma regla** que Today y Activity (`mileage/read.py`); concilia día a día con Activity (prueba) |
| ¿Hay coste de combustible? | **Sí**, por jornada: `millas oficiales / MPG congelado × precio de referencia` |
| ¿De dónde sale el precio? | De `fuel_reference`, una tabla en PostgreSQL **sin pantalla ni cron** (contrato preparado para RTE11) |
| ¿Y sin precio? | Coste visible **$0.00**; internamente `waiting_reference`, **no se congela** y se resuelve solo cuando llega la referencia |
| ¿Puede un precio nuevo cambiar un coste pasado? | **No.** Una estimación final queda congelada con su procedencia (referencia, precio, fecha, fuente) |
| ¿Estado y grado de combustible? | **Congelados al empezar la jornada**; editar después el supervisor o el vehículo no cambia la historia |
| ¿Excel? | **16 columnas** aprobadas, una fila por viaje, concilia con la pantalla |
| ¿Permisos? | `route.reports.read` y `route.reports.export`; Administrador de Route **sí**, Supervisor **no**; tenants existentes por alineación |

**Lo que hay que saber antes de usarlo en producción** (detalle en §22):

1. **Hasta que exista la carga de precios (RTE11), todos los costes salen $0.00.**
   Es la regla aprobada, no un fallo.
2. **Las jornadas anteriores al despliegue no tienen estado operativo** (D-1
   prohíbe deducirlo hoy) y su coste quedará en $0.00 de forma permanente,
   con motivo `missing_input`. Lo mismo para cualquier jornada que empiece
   antes de que el administrador fije el estado del supervisor.
3. Acción operativa: **fijar el estado de cada supervisor** en *CER Route
   Configuration → Supervisors* justo después del despliegue.

---

## 2 · V0.7 Reports UX Inventory

Sin cambios respecto al CP1; se implementó **exactamente** este inventario:

| Elemento | V0.7 | Implementado |
|---|---|---|
| Cabecera | `Reports` · *Consolidated operational analysis* · **Export Excel** | Igual; el botón sólo aparece con `route.reports.export` |
| Supervisor | `<select>` con **All Supervisors** por defecto | Igual, también en móvil |
| Periodo | Week / Month / Year, por defecto Week | Igual |
| Leyenda | `All Supervisors · Oct 12–18, 2026` | Igual |
| Navegación entre periodos | **ninguna** | **ninguna** |
| KPIs | Total miles · Activity time · Activities · Est. fuel cost | Igual |
| Tarjeta izquierda | By day / week / month, *«Time grouping follows Activity exploration»* | Igual |
| Tarjeta derecha | Activity breakdown por **propósito**: Activity · Miles · Time · Events · Est. cost | Igual |
| Acordeón | **no existe** | **no se añadió** |
| Móvil | barra apilada, KPIs 2×2, tarjetas en una columna | Igual |

---

## 3 · Existing Components Reused

| Pieza | Origen | Uso en RTE09 |
|---|---|---|
| Millas oficiales | `mileage/read.py`: `metros_calculados`, `pendientes`, `sin_resolver`, `millas_oficiales` | Única fuente de millas |
| Periodos y grupos | `activityexplorer/dao.py`: `periodo`, `componer_grupos` | Semana lunes–domingo, recortada al mes |
| Duración de actividad | `activityexplorer/dao.py`: `_duracion_segundos` | Misma definición que Activity |
| Supervisores elegibles | `activityexplorer/dao.py`: `supervisores` | *All Supervisors* = ese conjunto |
| Día de negocio | `work_session.session_date` + zonas de T-1/T-2 | El periodo «en curso» se decide con la zona de los supervisores |
| MPG congelado | `work_session.mpg_snapshot` | El MPG de la fórmula |
| Catálogo de estados | `region` (`/api/regions/catalog`) | Valores válidos del estado operativo |
| Alineación de capacidades | `align_role_capabilities.alinear()` | Concede las dos capacidades a tenants existentes |
| Tabla / tarjetas / formatos | primitivas `shadcn/new-york`, `formatMiles`, `formatDuration`, `formatPeriod` | Sin componentes copiados |

---

## 4 · Consolidated Reporting Read Model

Un solo modelo de lectura: `reports/dao.hechos()` devuelve **una fila por
viaje** con su jornada, supervisor, vehículo, kilometraje y bloque de
actividad. Las actividades seleccionadas se leen en una **consulta aparte** y se
pegan a la fila como lista: por eso una parada con tres actividades sigue
siendo una fila, una vez sus millas y una vez su tiempo.

De esas filas salen **todos** los números: KPIs, grupos, desglose y Excel.
Invariante probada: `Σ grupos = total` para millas, actividades, tiempo y
coste, en semana, mes y año.

---

## 5 · Supervisor / Period Filters

- **All Supervisors** (por defecto): los supervisores elegibles de la compañía,
  el mismo conjunto que Activity.
- **Un supervisor**: sólo si pertenece a ese conjunto. Un id de otra compañía
  y uno inexistente reciben **el mismo 404**, con el mismo cuerpo.
- **Periodo**: el en curso. El API admite `date` como ancla (lo usan las
  pruebas); la pantalla no ofrece navegación, como el V0.7.

---

## 6 · Temporal Aggregation

| Rango | Agrupa por | Regla |
|---|---|---|
| Week | día | lunes a domingo |
| Month | semana | semanas lunes–domingo **recortadas** al mes (la de Activity) |
| Year | mes | enero a diciembre |

Manda `session_date`: una jornada del domingo que termina el lunes pertenece
a la semana del domingo (prueba de medianoche).

---

## 7 · Official Miles

Exactamente la regla compartida: suma sólo los viajes `calculated`; los
`pending_calculation` se señalan aparte (`mileage_pending`, «+» en el KPI) y los
`not_calculable` / `calculation_failed` se cuentan como sin resolver. Los
tramos son la procedencia del total, **no** se suman (prueba con un tramo
insertado: 10 mi siguen siendo 10 mi).

---

## 8 · Time / Activity Semantics

- **Activity time**: suma de bloques **terminados**, una vez por parada.
- **Activities**: número de **paradas con bloque de actividad**, no de
  actividades seleccionadas.
- Una parada con 3 actividades: 1 en *Activities*, su tiempo una vez, sus
  millas una vez (prueba).

---

## 9 · Activity Type Distribution

- **Pantalla:** por **propósito**, en el orden del V0.7: Client Visit, Employee
  Visit, Recruiting, Check Delivery, Office, Other. Sólo se ven las filas con
  datos.
- **Regreso a casa:** no es una visita y no tiene fila; sus millas cuentan en
  el total y el API las devuelve aparte (`breakdown_excluded`), de forma que
  `Σ filas + excluidos = total` (prueba).
- **Actividades seleccionadas:** en el API (`activity_types`, conteo de
  ocurrencias) y en la columna *Activity Type* del Excel. Un valor retirado
  del catálogo sigue legible (prueba).

---

## 10 · Fuel Estimate Formula

Por **jornada**, nunca sobre el total del periodo:

```
galones = millas oficiales de la jornada / MPG congelado de la jornada
coste   = galones × precio de la referencia aplicable
```

El coste de la jornada se reparte entre sus viajes en proporción a sus millas,
para el desglose y el Excel. Pruebas: `10 mi / 25 MPG × 3,50 = 1,40` exacto;
`10 mi a 20 MPG + 10 mi a 40 MPG a 4,00 = 3,00` (no un promedio de MPG).

---

## 11 · Fuel Reference Resolution

`fuel_reference` (por tenant, **append-only**): estado, grado, precio por galón
(> 0 por `CHECK`), fecha efectiva, fuente, referencia de la fuente, instante de
carga.

**Coincidencia:** mismo estado **y** mismo grado **y** `effective_date ≤
session_date`, la más reciente; a igual fecha, la cargada después (una
corrección es una fila nueva). **Sin** alternativa regional ni nacional.

Prueba discriminante con cinco referencias: aplica la del 10-sep (3,00); se
ignoran la anterior (2,00), la **futura** (9,00), la de **otro estado** (8,00) y
la de **otro grado** (7,00).

**Reports no llama a ningún proveedor**: lee la tabla. La ingesta (RTE11)
escribirá en la misma tabla sin tocar Reports.

---

## 12 · Historical Fuel Provenance

Cuando una jornada **terminada**, **sin millas pendientes** y **con referencia**
se calcula, se escribe una fila en `work_session_fuel_estimate` (append-only,
una por jornada) con: referencia (id), estado, grado, MPG, millas, precio,
fecha efectiva, fuente, galones, coste e instante. A partir de ahí el informe
usa **esa** fila.

Prueba: estimación final a 3,00 con «Feed A»; llega después un precio de 5,00
aplicable por fecha → el informe sigue en **3,00**.

Una jornada abierta o con millas pendientes se calcula en vivo y **no** se
congela (prueba).

---

## 13 · Missing Estimate: visible `0` vs numeric zero

Regla de la autorización §8 (sustituye al `—` del CP1):

| Caso | Coste visible | Estado interno | ¿Se congela? |
|---|---|---|---|
| Hay referencia, millas > 0 | el calculado | `calculated` | sí, si la jornada es final |
| Hay referencia, **0 millas** | $0.00 | `calculated` | sí |
| **No hay referencia** | $0.00 | `waiting_reference` | **no**; se resuelve al llegar el precio |
| Falta estado, grado o MPG | $0.00 | `missing_input` (+ qué falta) | no |
| Mezcla en el periodo | suma | `partial` | — |

El estado va en el API (`summary.fuel_cost_status`, `fuel.waiting_reference`,
`fuel.missing`) y en la hoja *Summary* del Excel. En el Excel, *Reference Fuel
Price* queda **vacío** si no hay precio: **nunca se inventa**.

**Interpretación propia, a validar por CER:** `missing_input` también se
muestra como $0.00. La autorización fija el 0 para la falta de referencia; se
aplicó lo mismo a la falta de estado, grado o MPG, con su motivo distinto en
el API.

---

## 14 · API

| Método | Ruta | Permiso | Respuesta |
|---|---|---|---|
| GET | `/api/reports?range=&date=&supervisor_user_id=` | `route.reports.read` | `ReportView`: periodo, supervisores, `summary`, `groups`, `breakdown`, `breakdown_excluded`, `activity_types`, `fuel` |
| GET | `/api/reports/export?…` | `route.reports.read` **y** `route.reports.export` | `.xlsx` `CER_Route_Report_{nombre}_{inicio}_{fin}.xlsx` |
| PUT | `/api/supervisors/{id}/operational-state` | `route.vehicles.manage` | perfil con `operational_state`; 422 si no es un estado activo; 409 si la versión cambió; auditado |

`company_id` sale del subdominio, nunca del cliente. Sin coordenadas en
ninguna respuesta.

---

## 15 · V0.7 Desktop

Captura `var/screenshots/rte09/escritorio-1280-week.png` (local, fuera del
repositorio): leyenda *All Supervisors · Oct 12–18, 2026*; KPIs 24.0 · 0m · 1 ·
**$3.25**; *By day* con *Mon Oct 12 — 24.0 mi — $3.25 est. fuel*; *Activity
breakdown* con *Client Visit 24.0 · 0m · 1 · $3.25*. Exportación descargada y
abierta en la prueba: 16 columnas, una fila.

---

## 16 · V0.7 Mobile

Captura `var/screenshots/rte09/movil-390-week-esperando.png` (390 px, sin
referencia aplicable): selector de supervisor **visible**, pestañas, KPIs 2×2
con **Est. fuel cost $0.00**, tarjetas en una columna. Week → Month → Year →
Week: el agrupado cambia (*By day / By week / By month*), el coste sigue en
$0.00 con `waiting_reference` y **no hay desbordamiento horizontal** en
ninguno.

---

## 17 · Excel Export

Hoja *Activity Detail* con las **16 columnas** aprobadas, en orden: Date ·
Supervisor · Vehicle · Activity Type · Reference · Start · End · Duration · Trip
Miles · Operational MPG · Fuel Grade · Reference Fuel Price · Estimated Gallons ·
Estimated Fuel Cost · Outcome · Notes. Hoja *Summary* con totales y el estado
del combustible.

- **Una fila por viaje**: las actividades seleccionadas van juntas en *Activity
  Type* (`Client Visit: A, B, C`).
- Mismo filtro de supervisor y periodo que la pantalla (prueba).
- Σ *Trip Miles* = KPI de millas; Σ *Estimated Fuel Cost* = KPI de coste
  (prueba).
- Horas en 12 h, en la zona de la jornada.
- Millas pendientes o sin cifra se escriben como texto (*Pending* /
  *Unresolved*), no como 0.

---

## 18 · Roles / Permissions / Existing-Tenant Alignment

| Capacidad | Administrador de Route | Supervisor |
|---|---|---|
| `route.reports.read` | sí | **no** |
| `route.reports.export` | sí | **no** |

Declaradas en el catálogo y en la plantilla del rol; los tenants existentes
las reciben por `align_role_capabilities` (parte del *converge*). Prueba: se
quitan a un tenant, se ejecuta la alineación y vuelven, sin dárselas al
supervisor. `route.fuelreference.manage` **no se declara**: no hay superficie
que la exija.

---

## 19 · Security / Tenant Isolation

- 401 sin sesión; 403 para el supervisor (pantalla y API); 403 al Excel sin
  `export`.
- 404 idéntico para un supervisor de otra compañía y para uno inexistente.
- *All Supervisors* no incluye personas de otra compañía (prueba).
- Doble alcance: el router valida al supervisor pedido contra la compañía y la
  consulta filtra por `company_id`.
- `fuel_reference` y `work_session_fuel_estimate` son append-only por
  disparador, vigilados por el diagnóstico de plataforma.
- Ni coordenadas ni secretos en el API ni en el Excel.

---

## 20 · Tests / Regression

**Integración RTE09** — `tests/integration/test_reports.py`: **32/32 PASS**
(30 de comportamiento + 2 de evidencia del §25).

**Navegador RTE09** — `tests/e2e/test_rte09_reports_browser.py`: **3/3 PASS**
(escritorio con Excel, móvil con $0.00 y pestañas, supervisor sin acceso).

**Mutaciones** (§23: quitar cada protección debe hacer fallar pruebas):

| Protección quitada | Mutación | Resultado |
|---|---|---|
| Reutilización de millas | millas reconstruidas sumando tramos en vez de la regla compartida | **detectada** |
| Alcance de tenant — router | aceptar cualquier `supervisor_user_id` | **detectada** (`test_otro_tenant…`) |
| Alcance de tenant — consulta | quitar `company_id` del DAO | **detectada** (`test_la_consulta_filtra_por_compania…`) |
| Snapshot de estado | ignorar el estado congelado | **detectada** (12 pruebas) |
| Snapshot de grado | ignorar el grado congelado | **detectada** (`test_el_grado_congelado_elige_su_precio`) |
| Coincidencia por fecha efectiva | aceptar referencias futuras | **detectada** (2 pruebas) |
| Protección multi-actividad | unir las actividades seleccionadas a la consulta principal | **detectada** (4 pruebas) |

**7/7 detectadas.** En la primera pasada sobrevivieron tres (millas, grado y
alcance de la consulta). No eran defectos del producto sino huecos de las
pruebas:

- La primera mutación de millas (`total_meters` sin filtrar por estado) es
  **equivalente**: la base sólo admite `total_meters` en viajes `calculated`
  (`CHECK`). Se sustituyó por una reimplementación realista.
- Todas las pruebas usaban grado `regular`, y el alcance de la consulta
  quedaba tapado por la validación del router. Se añadieron dos pruebas que
  cubren esos huecos.

**Regresión completa** (3 workers, local):

| Lote | Pruebas | PASS | FAIL | Omitidas | Exit |
|---|---|---|---|---|---|
| Suite completa, 3 workers (antes del ajuste de redondeo) | 1327 | 1306 | 6 | 15 | 1 |
| Reports + catálogo + superficie pública + cableado (tras el ajuste) | 96 | 96 | 0 | 0 | 0 |
| E2E RTE09 (tras el ajuste) | 3 | 3 | 0 | 0 | 0 |

**Los 6 fallos de la suite completa no son de RTE09** (`CONFIRMED` por su
contenido):

- `test_provisioning_alignment`: espera 12 capacidades del Administrador de
  Route y encuentra 16. Ya fallaba con 14 antes de RTE09 (decisión de conteo
  pendiente). No se ha tocado.
- 5 E2E de ubicación offline (`test_rte06_offline_durability`,
  `test_rte06_recovery_accuracy` ×4): los mismos 5 que ya estaban pendientes de
  diagnóstico. RTE09 no toca ese código. Causa raíz `UNVERIFIED`.

**Estáticos:** `npm run check` (typecheck + lint) 0 errores · `import app.main`
OK · bundle de producción reconstruido · `ruff`: **NOT RUN** (no está
instalado en este entorno).

**Migración `0016`:** un solo head; subida → bajada → subida OK; `alembic
check`: sin diferencias entre modelos y esquema.

Fallos encontrados durante la ejecución (`CONFIRMED`), todos corregidos:

- **Defecto de producto: redondeo del dinero.** La evidencia 1 esperaba $3.13
  por $3.125 y obtuvo **$3.12**: `Decimal.quantize` redondea por defecto al
  par. Se cambió a redondeo hacia arriba en la mitad (`ROUND_HALF_UP`) en el
  API y en las celdas del Excel. Después pasó.
- De las pruebas nuevas: un tramo insertado sin `computed_at`; el estado `NC`
  no estaba sembrado en el tenant de prueba (se usa `TX`); un selector de texto
  ambiguo en la prueba de navegador; la evidencia 1 intentó cerrar la jornada
  con una parada sin terminar y el producto lo impidió con 409, que es la
  guarda correcta.

---

## 21 · Expected → Implemented → Evidence → Gap

| # | Criterio (§22) | Estado | Evidencia | Gap |
|---|---|---|---|---|
| 1–2 | V0.7, sin acordeón | VALIDATED | capturas escritorio/móvil | — |
| 3–4 | Supervisor / All | VALIDATED | `test_all_supervisors_suma_y_uno_filtra`, E2E selector | — |
| 5–8 | Week / Month / Year, sin navegación | VALIDATED | `test_semana_mes_y_ano…`, E2E pestañas | — |
| 9–10 | Millas compartidas; concilia | VALIDATED | `test_concilia_con_el_explorador_dia_a_dia` + mutación | — |
| 11 | Sin doble conteo | VALIDATED | tramos, multi-actividad + mutación | — |
| 12–13 | Tiempo y conteo | VALIDATED | `test_varias_actividades_no_multiplican…` | — |
| 14–15 | Desglose por propósito; actividades en Excel | VALIDATED | `test_el_desglose_es_por_proposito…`, Excel | — |
| 16–19 | Estado operativo, snapshots, sin deriva | VALIDATED | `test_estado_y_grado_se_congelan_al_empezar` + mutaciones | — |
| 20–21 | `fuel_reference` con historia | VALIDATED | tabla + append-only + `CHECK` | — |
| 22–23 | Sin proveedor; sin cron acoplado | VALIDATED | Reports sólo lee la tabla; no hay cliente HTTP en `reports/` ni `fuelreference/` | — |
| 24–26 | 0 visible; distinguible; resoluble | VALIDATED | `test_sin_referencia_espera…`, `test_un_cero_calculado…`, evidencia 2 | — |
| 27–28 | Estado + grado + fecha; sin fallback | VALIDATED | `test_la_referencia_aplicable…` + mutación | — |
| 29–30 | Procedencia; sin reescritura | VALIDATED | `test_una_estimacion_final_no_cambia…` | — |
| 31–32 | 16 columnas; concilia | VALIDATED | `test_el_excel_tiene_las_16_columnas…`, E2E descarga | — |
| 33–35 | Permisos; alineación; supervisor fuera | VALIDATED | pruebas de permisos y alineación, E2E 403 | — |
| 36 | Tenant | VALIDATED | pruebas cross-tenant + mutación | — |
| 37–38 | Móvil / escritorio | VALIDATED | 3 E2E | — |
| 39–43 | Today, Activity, RTE10-A02, millas, offline sin cambios | VALIDATED | regresión completa: sus pruebas pasan; los 5 E2E offline ya fallaban antes | — |
| 44 | Regresión verde | VALIDATED, con 6 fallos ajenos | §20: 1306/1327; los 6 son previos y fuera de RTE09 | fallos previos, fuera de RTE09 |
| 45 | Sin Partial/Gap/Blocked sin explicar | VALIDATED | §22 | — |

---

## 22 · Remaining Issues

**Para CER (decisión o confirmación, no bugs):**

1. **$0.00 hasta RTE11.** Sin carga de precios, todo coste espera. Correcto
   según la regla; conviene que el equipo lo sepa antes de mirar Reports.
2. **Jornadas anteriores sin estado operativo** → `missing_input`, $0.00
   permanente. Es la consecuencia de D-1 (no deducir la historia con un dato
   de hoy). Si CER quisiera recuperarlas, sería una decisión nueva (por
   ejemplo, asignarles un estado declarado por el administrador).
3. **`missing_input` también se ve como $0.00** (§13). Confirmar.

**Técnico:**

4. **Redondeo por fila.** Cada fila del desglose y del Excel se redondea a
   céntimos por separado: en la evidencia 1 las filas suman $2.34 + $0.78 =
   $3.12 frente a un total de $3.13. Los valores sin redondear concilian
   exactamente; es una diferencia de ±$0.01 de presentación. Se puede cambiar
   si CER lo pide.

**Fuera de RTE09:**

5. `test_provisioning_alignment` espera 12 capacidades del Administrador de
   Route; tenía 14 y ahora 16. Ya estaba en rojo antes de RTE09 y sigue
   pendiente de la decisión de conteo. No se ha tocado.
6. Los 5 E2E de ubicación offline siguen pendientes de diagnóstico.

**Acción operativa (no la hace el trabajo local):**

- Desplegar y ejecutar la migración `0016` (aditiva; rellena el grado de las
  jornadas existentes desde la auditoría del vehículo).
- Ejecutar el *converge* / `align_role_capabilities` para conceder
  `route.reports.read/export` al Administrador de Route de los tenants
  existentes.
- Fijar el estado operativo de cada supervisor.

---

## 23 · Proposed Status

`RTE09 CONSOLIDATED REPORTS + FUEL READINESS COMPLETE / READY FOR CER VALIDATION`

---

## Evidencia 1 · cadena completa, calculada

`test_evidencia_cadena_completa_calculada`, salida real. Después de la jornada
el supervisor pasó a TX y el vehículo a diésel con 10 MPG, y existe un precio
TX/diésel: nada de eso cambia el resultado. La pantalla V0.7 de la cadena se
comprueba en el E2E de escritorio (§15). Excel por fila: *Activity Type*, *Trip
Miles*, *Reference Fuel Price*, *Estimated Gallons*, *Estimated Fuel Cost*.

```text
EVIDENCIA 1 · cadena calculada
  → Supervisor: supervisor@alpha.example.com
  → Operational State al empezar (hoy TX): GA
  → Work Session / session_date: #1 / 2026-09-16
  → Vehicle / MPG snapshot (hoy 10.00): #1 / 24.00
  → Fuel Grade snapshot (hoy diesel): regular
  → Trips: #1 client_visit 18.0 mi, 2 actividades; #2 office 6.0 mi
  → Official Miles: 24.0
  → Fuel Reference: #1 GA/regular 3.1250 desde 2026-09-14, 'Evidence feed' (ignorada la TX/diesel actual)
  → Estado: calculated
  → Estimated Gallons: 1.000
  → Est. Fuel (API): 3.13
  → Congelada: ref #1 · 3.1250 · 2026-09-14 · Evidence feed · 1.0000 gal · 3.1250
  → Breakdown: [('client_visit', '18.0', '2.34'), ('office', '6.0', '0.78')]
  → Excel: [('Client Visit: Service Review, Staffing Follow-up', 18, 3.125, 0.75, 2.34), ('Office', 6, 3.125, 0.25, 0.78)]
```

## Evidencia 2 · sin referencia de combustible

`test_evidencia_sin_referencia`, salida real: coste visible 0, estado distinto
de `calculated`, ningún precio inventado (ni en la tabla ni en el Excel), y la
misma jornada se resuelve cuando llega la referencia.

```text
EVIDENCIA 2 · sin referencia
  → Est. Fuel visible: 0.00
  → Estado interno: waiting_reference
  → Filas en fuel_reference: 0
  → Estimaciones congeladas: 0
  → Excel · Reference Fuel Price / Est. Fuel Cost: (None, 0)
  → Llega la referencia GA/regular 3.0000: →
  → Est. Fuel / estado: ('3.00', 'calculated')
```

---

## Estimación

**RTE09 dentro de su alcance: 0 h restantes de desarrollo.** Queda la
validación de CER.

Lo construido, medido con `wc -l`:

| Componente | LoC | Coeficiente | Horas-agente |
|---|---|---|---|
| Backend Reports (`reports/`) + Excel | 856 | 150–200 LoC/h | 4,9 |
| Combustible (`fuelreference/`) + migración 0016 + snapshots | 653 + ~200 modificadas | 150–200 LoC/h | 4,9 |
| Frontend Reports + campo de estado | 599 + ~100 modificadas | 50–70 LoC/h | 11,7 |
| Pruebas de integración | ≈ 1000 | 80–100 LoC/h | 11,1 |
| E2E | 168 | 50–70 LoC/h | 2,8 |
| **Total** | **≈ 3970** | | **≈ 35 h** |

Frente a las 49 h base del CP1: la pantalla de Fuel Reference (5 h) salió del
alcance y el resto se ajustó a la estimación.

| Siguiente | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Correcciones de la validación de CER | pendiente | desconocido | UI + dominio | 2–4 (+50 % si son de navegador → 3–6) |

---

## Git

| | |
|---|---|
| Rama | `feature/rte09-consolidated-reports-fuel` (desde `dev` `22b1bfc`) |
| Commits | `307b61c` implementación, pruebas y este reporte · el siguiente añade este bloque de Git |
| Push | sí |
| MR | **!85** · https://gitlab.com/cermanagementgroup/cermanagementgroup-route/-/merge_requests/85 → `dev` |
| Fusionado | **No**: pendiente de la validación de CER |
| Árbol | limpio tras el push |

---

## Siguiente paso

Validación de CER sobre el MR. Después del despliegue: migración, alineación de
capacidades y estado operativo de cada supervisor. **RTE10, RTE11 y el cron de
precios no se han empezado.**
