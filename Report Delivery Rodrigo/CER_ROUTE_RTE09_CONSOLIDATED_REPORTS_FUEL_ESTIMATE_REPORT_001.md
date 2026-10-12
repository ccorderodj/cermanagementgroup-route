# CER Route · RTE09 · Consolidated Reports + Fuel Estimate

**Reporte 001** · 12 de octubre de 2026 · **Etapa: RTE09-CP1** (inventario V0.7 + auditoría de datos)
**Instrucciones:** `CER_ROUTE_RTE09_CONSOLIDATED_REPORTS_FUEL_ESTIMATE_INSTRUCTIONS_001.md`
**Base:** `dev` en `5a78f52`

---

## Proposed Status

`RTE09 BLOCKED — CER DECISION REQUIRED`

El CP1 encontró **tres decisiones de producto genuinas** (§4) que cambian el
modelo de datos, el contrato y la pantalla. Construir sobre una suposición
obligaría a rehacer. Todo lo que es decisión técnica —y es mucho— queda
**decidido** en §5, para que con las respuestas la implementación empiece sin
más preguntas.

**No se ha escrito código de producto.** Este documento es el entregable del
CP1; el reporte final de RTE09 sustituirá a éste en el mismo archivo.

---

## 1 · Executive Result

| Pregunta | Respuesta |
|---|---|
| ¿Existe un dominio de referencia de combustible? | **No.** Ni tabla, ni precios, ni historial |
| ¿La jornada congela el MPG? | **Sí** (`work_session.mpg_snapshot`) |
| ¿La jornada congela el **grado** de combustible? | **No.** Editar el grado de un vehículo cambiaría informes pasados: **brecha que §18 ordena cerrar** |
| ¿Algo liga una jornada a una **geografía**? | **No.** Ni la jornada, ni el supervisor, ni el vehículo |
| ¿Qué dice la compañía real? | Declara **un solo estado (GA)**; sus vehículos son **GA-…, NC-… y SC-…** |
| ¿Tiene Reports acordeón en V0.7? | **No** (§2) |
| ¿Hay capacidades previstas? | Sí: RTE01 certificó `route.reports.read`, `route.reports.export` y `route.fuelreference.manage`, sin declarar hasta que exista su superficie |

---

## 2 · V0.7 Reports UX Inventory

Fuente: `04_Mockup_Reference_V0_7/standalone.html`, funciones `adminReports`,
`reportTimeline`, `reportActivityTable`, `exportExcel` y CSS `.report-*`.

| Elemento | V0.7 |
|---|---|
| Cabecera | `Reports` · *Consolidated operational analysis* · botón primario **Export Excel** |
| Supervisor | `<select>` con **All Supervisors** (por defecto) + cada supervisor |
| Periodo | pestañas **Week / Month / Year** (por defecto Week) |
| Leyenda | `{All Supervisors / nombre} · {periodo, p. ej. Sep 14–20, 2026}` |
| **Navegación entre periodos** | **ninguna**: sin anterior/siguiente; se ve el periodo actual |
| KPIs (4) | Total miles · Activity time · Activities · Est. fuel cost |
| Tarjeta izquierda | **By day / By week / By month** según rango: filas con fecha, `N activities · tiempo`, `X mi`, `$Y est. fuel` · *«Time grouping follows Activity exploration»* |
| Tarjeta derecha | **Activity breakdown**: tabla Activity · Miles · Time · Events · Est. cost, con barra proporcional |
| Filas de la tabla | **Client Visit, Employee Visit, Recruiting, Check Delivery, Office, Other**: son los **propósitos de viaje** |
| Móvil | barra apilada; **en Reports los campos sí se muestran** (`.report-toolbar .fields-inline{display:block}`); KPIs a 2 columnas; tarjetas a 1 columna |
| **Acordeón** | **No existe en Reports**. El único despliegue del V0.7 es la jerarquía de Activity, que ya está construida |
| Export del mockup | 11 columnas, `.xls` SpreadsheetML |
| Configuración → Fuel Reference | precios por grado, fuente, fecha efectiva, ámbito (*Georgia*), **Save reference prices** e **historial** |

**Discrepancias con la instrucción**, que se resuelven así salvo que CER diga
otra cosa:

- **Acordeón:** la instrucción lo menciona, pero el V0.7 de Reports no lo tiene.
  §3 de la instrucción: *«si el mockup contiene un detalle, el mockup gana»*.
  **Se reproduce el V0.7: sin acordeón.** Ver D-4.
- **Columnas del Excel:** la instrucción aprueba 16 columnas explícitas, frente a
  las 11 del mockup. **Gana la instrucción**: es una regla de producto
  explícita.
- **Fuel no disponible:** D-06 de RTE01 decía *Pending Calculation*; la §12 de
  RTE09, posterior y explícita, dice `—`. **Se aplica `—`**, con el motivo en el
  API (`unavailable_reason`).

---

## 3 · Auditoría del modelo actual

| Pieza | Estado | Qué hace falta |
|---|---|---|
| Millas oficiales | `mileage/read.py`: `metros_calculados`, `pendientes`, `sin_resolver`, `millas_oficiales` | **Reutilizar**; ninguna fórmula nueva |
| Día de negocio | `work_session.session_date` (y la zona de T-1/T-2) | Reutilizar |
| Agrupación por periodo | `activityexplorer.dao.periodo` y `componer_grupos` (semana lunes–domingo recortada al mes) | **Reutilizar** —el V0.7 dice *«Time grouping follows Activity exploration»*— |
| Activity time | Explorer: suma de bloques **terminados** | Reutilizar la misma definición |
| Vehículo + MPG | snapshot en la jornada | Reutilizar |
| **Grado de combustible** | **sólo en el vehículo actual** | **Snapshot en la jornada** (cierra §18) |
| **Referencia de combustible** | **inexistente** | Dominio nuevo (§5.2) |
| **Geografía de la jornada** | **inexistente** | Depende de **D-1** |
| Estados de la compañía | `company_state`: GA, principal | No representa dónde trabaja cada supervisor (§4, D-1) |
| Excel | **ninguna librería** en el proyecto | `openpyxl` (§5.5) |
| Capacidades | `route.reports.read/export`, `route.fuelreference.manage` previstas | Declararlas + **alineación de tenants existentes** (§5.6) |

Datos reales (copia local de `cerroute`): 107 ejecuciones de actividad, de las
que **1** tiene varias actividades seleccionadas; viajes por propósito: Client
Visit 60, Office 23, Home 19, Other 17, Employee Visit 4, Recruiting 4, Check
Delivery 2.

---

## 4 · Decisiones de CER necesarias

### D-1 · ¿Qué geografía tiene una jornada? · **bloquea el coste**

**Hecho.** D-06 exige que el precio dependa de la geografía, pero nada en el
modelo sitúa una jornada en un lugar. La compañía real declara sólo GA y tiene
supervisores en Carolina del Norte y del Sur.

**Impacto.** Decide qué precio paga cada milla. Elegir mal da costes
plausibles y falsos, que es peor que `—`.

| Opción | Cómo | A favor | En contra |
|---|---|---|---|
| **A** · Estado operativo del supervisor | un campo **opcional** en el panel de supervisores (como la zona horaria), congelado en la jornada al iniciar | determinista; no depende del GPS; encaja con la flota real (un estado por vehículo/supervisor) | un supervisor que cruza de estado se valora con el suyo |
| **B** · Estado donde empieza la jornada | punto de `Start Work` → estado, con límites de estados **incluidos en la aplicación** (sin proveedor externo), congelado | refleja dónde estaba de verdad | sin ubicación en `Start Work` no hay coste; añade un fichero geográfico |
| C · Estado principal de la compañía | `company_state.is_main` | cero esfuerzo | **los datos reales lo descartan**: GA para todos |

**Recomendación: A**, y B como mejora futura si CER quiere precisión por
desplazamiento. Sin estado configurado, el coste es `—`.

### D-2 · ¿Cómo entran los precios en RTE09? · **bloquea que el coste exista**

**Hecho.** No hay ningún precio. D-06 delegó la **fuente** en el desarrollo,
pero RTE09 deja la **ingesta automática** fuera (§6) y el V0.7 dibuja una
pantalla de configuración manual con historial. Sin una forma de entrada,
**todos** los costes saldrían `—` en producción.

| Opción | Qué entrega |
|---|---|
| **A** · Pantalla **Fuel Reference** del V0.7 | el administrador registra precio por grado, estado, fecha efectiva y fuente; historial; `route.fuelreference.manage`; auditada |
| B · Importación CSV por comando | operación técnica, sin pantalla |
| C · Ingesta programada (EIA) | automática, pero EIA no publica GA, NC ni SC por estado: sólo la región *Lower Atlantic* (exigiría aprobar D-3) |

**Recomendación: A**, que ya está diseñada en el V0.7. El contrato queda
preparado para que B o C escriban en la misma tabla más adelante sin tocar
Reports.

### D-3 · ¿Se admite un precio de ámbito mayor si falta el del estado?

**Hecho.** La instrucción prohíbe sustituir un precio nacional o por defecto
salvo regla aprobada.

**Recomendación:** **no** por ahora: sólo coincidencia exacta de estado, grado y
fecha vigente. Si se elige D-2 C, habrá que aprobar el uso de la región.

### D-4 · ¿Qué es «Activity Type» en la distribución?

**Hecho.** La tabla *Activity breakdown* del V0.7 desglosa por **propósito de
viaje** (Client Visit, Office…), con millas, tiempo, eventos y coste por fila.
La instrucción pide la distribución por **tipo de actividad seleccionado**
(Service Review, Staffing Follow-up…), que admite varios por parada y **sólo
puede contar ocurrencias**, nunca millas ni tiempo, sin multiplicarlos.

| Opción | Pantalla | Excel / API |
|---|---|---|
| **A** · V0.7 tal cual | tabla por **propósito**, con millas/tiempo/eventos/coste | columna *Activity Type* con las actividades seleccionadas; el API devuelve además los conteos por actividad |
| B · Tabla por actividad seleccionada | sólo conteos: se pierden millas, tiempo y coste por fila del V0.7 | igual |
| C · Las dos | la tabla del V0.7 y un desglose nuevo | **añade UI que el V0.7 no tiene** |

**Recomendación: A.** Respeta el V0.7 y PR-04 (propósito y actividad distintos),
no multiplica nada y deja los conteos por actividad en el API y el Excel.
**Sin acordeón**, como el V0.7.

### Confirmación menor · navegación entre periodos

El V0.7 no la tiene: Reports muestra la semana, el mes o el año **en curso**. Se
reproduce así. El API acepta fecha ancla igualmente, por si CER quisiera
navegación más adelante (sería UI nueva).

---

## 5 · Lo que queda decidido técnicamente

### 5.1 · Un solo modelo de lectura

`reports` sobre los mismos hechos y las **mismas funciones** que Explorer:
millas de `mileage/read.py`, periodos y grupos de `activityexplorer`, tiempo
como suma de bloques terminados. Una consulta agrupada por
`(session_date, supervisor, propósito)` y otra por actividad seleccionada para
los conteos; la tarjeta *By …*, los KPIs y la tabla se componen de ahí, y el
**Excel sale del mismo resultado**. Invariante probada: `Σ grupos = total`.

### 5.2 · Referencia de combustible

Tabla `fuel_reference` **por tenant**: grado, estado, fecha efectiva, precio
(4 decimales), fuente, quién y cuándo. **Sólo se añaden filas**: corregir un
precio es registrar uno nuevo, nunca reescribir el anterior.

**Resolución:** el precio vigente es el del mismo estado y grado con la fecha
efectiva más reciente que no sea posterior a la `session_date`.

### 5.3 · Estabilidad histórica

Por **jornada**, una vez resueltas sus entradas, se congela en
`work_session_fuel_estimate`: millas usadas, MPG, grado, estado, referencia
(id), precio, fecha efectiva, fuente, galones, coste e instante de cálculo. Un
precio importado después **no** reescribe una estimación ya resuelta. Una
jornada con millas aún pendientes no se congela hasta que se resuelvan.

Se calcula **por jornada y luego se suma**: nunca
`millas del periodo / un MPG × un precio` (§19).

### 5.4 · Grado e histórico

`work_session.fuel_grade_snapshot` (y el estado de D-1) se congelan en
`Start Work`, igual que el MPG. Migración aditiva: columnas `NULL`; para las
jornadas existentes el grado se rellena **desde su vehículo congelado**, que es
el mismo dato vigente hoy, documentado en la migración.

### 5.5 · Excel

`.xlsx` con `openpyxl` (dependencia nueva), una fila por viaje con las 16
columnas aprobadas. Las actividades seleccionadas se juntan en *Activity Type*,
en **una** fila, para no duplicar millas ni duración. El combustible no
disponible queda como **celda vacía**, nunca `0`. Mismo permiso y mismo filtro
que la pantalla.

### 5.6 · Permisos

`route.reports.read` (pantalla y API), `route.reports.export` (Excel) y, con
D-2 A, `route.fuelreference.manage`. Se conceden al rol Administrador de Route
y **no** al supervisor, y entran por la **ruta de alineación de tenants
existentes** (`align_role_capabilities`), no sólo por la siembra, para no
repetir el defecto de permisos obsoletos.

**Efecto conocido:** el rol Administrador pasa de 14 a 16 o 17 capacidades, y
`test_provisioning_alignment` —que ya falla con 14 frente a 12— seguirá en rojo
hasta que CER decida ese conteo. No se toca.

---

## 6 · Estimación con D-1 A, D-2 A, D-3 no y D-4 A

| Bloque | Volumen | Complejidad | Horas-agente |
|---|---|---|---|
| CP2 · modelo de lectura, filtros, periodos, permisos | ~450 LoC | dominio | 4,5 |
| CP3 · referencia de combustible, snapshots, resolución, congelado, migración | ~550 LoC | dominio | 6,0 |
| CP3 · pantalla Fuel Reference del V0.7 (D-2 A) | ~300 LoC | UI | 5,0 |
| CP4 · Reports V0.7 escritorio y móvil | ~450 LoC | UI | 7,0 |
| CP4 · Excel | ~200 LoC | integración | 2,5 |
| Pruebas de integración (§22) | ~1100 LoC | integración | 12,0 |
| E2E escritorio/móvil, Excel, `—` | ~400 LoC | navegador | 7,0 |
| CP5 · regresión, evidencia, reporte | — | — | 5,0 |
| **Subtotal** | **≈ 3450 LoC** | | **49,0** |
| **Con margen** (+10 % · +30 % · +50 %) | | | **≈ 62 h** |

D-1 B añade unas 6 h (límites de estados, resolución de puntos y sus pruebas).

---

## 7 · Git

| | |
|---|---|
| Rama | `docs/rte09-cp1-decision-gate` |
| Cambio | este documento y la instrucción; **ningún código** |
| Fusionado | No |

---

## 8 · Siguiente paso

Respuestas a **D-1, D-2, D-3 y D-4**. Con ellas se ejecutan CP2–CP5 y este
mismo archivo se convierte en el reporte final con las 23 secciones del §25.

Si CER prefiere avanzar mientras decide, **CP2** —modelo de lectura sin
combustible, filtros, periodos, totales y permisos— no depende de D-1, D-2 ni
D-3 y puede empezar ya; sólo el desglose de la tabla espera a D-4.
