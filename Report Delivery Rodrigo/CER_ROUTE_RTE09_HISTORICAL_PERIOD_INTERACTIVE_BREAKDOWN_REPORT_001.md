# CER Route · RTE09 · Enhancement 01 · Historical Period + Interactive Breakdown

**Reporte 001** · 12 de octubre de 2026
**Instrucciones:** `CER_ROUTE_RTE09_HISTORICAL_PERIOD_INTERACTIVE_BREAKDOWN_INSTRUCTIONS_001.md`
**Base:** `dev` en `1ece5c7` (RTE09 ya fusionado) · **Rama:** `feature/rte09-historical-period-breakdown`

---

## Proposed Status

`RTE09 HISTORICAL PERIOD + INTERACTIVE BREAKDOWN COMPLETE / READY FOR CER VALIDATION`

Propuesto, no declarado: **la certificación es de CER**. RTE09 no se da por
cerrado. No se ha empezado ningún otro checkpoint.

---

## 1 · Executive Result

| Pregunta | Respuesta |
|---|---|
| ¿Se puede revisar una semana, mes o año anterior? | **Sí**: selector de periodo concreto junto a Week / Month / Year |
| ¿Quién decide el periodo por defecto? | **El servidor** (día de negocio de T-1/T-2), nunca la fecha del navegador. Probado con el reloj del navegador en 2024 |
| ¿Se puede elegir un día, semana o mes de la tarjeta izquierda? | **Sí**: acota el *Activity Breakdown* a ese subgrupo |
| ¿Cambian los KPIs al elegir un subgrupo? | **No.** Siguen siendo del periodo principal |
| ¿Se puede volver al periodo entero? | **Sí**: *Whole week / month / year*, o volver a pulsar la fila |
| ¿Qué pasa al cambiar supervisor, tipo o periodo? | El subgrupo se **borra** siempre |
| ¿Y el Excel? | **Sin cambios**: exporta el periodo principal, aunque haya un subgrupo elegido |
| ¿Cambió algo del combustible, millas o permisos? | **No** |

---

## 2 · Previous vs New UX

| | Antes | Ahora |
|---|---|---|
| Periodo | sólo el en curso | el en curso por defecto, **o uno anterior** en su selector |
| Barra | Supervisor · Week/Month/Year · leyenda | Supervisor · Week/Month/Year · leyenda · **Week / Month / Year concreto** |
| Tarjeta izquierda | lista informativa | filas **elegibles** (botones), con marca *Selected* y *Whole …* |
| Activity Breakdown | siempre del periodo | del periodo **o** del subgrupo elegido, con la línea *Showing …* |
| KPIs | del periodo | **igual**: del periodo principal |
| Excel | del periodo en curso | del **periodo elegido**; nunca del subgrupo |
| URL | sin estado | `?range=&date=&supervisor=`: una recarga conserva el periodo |

Sin flechas anterior/siguiente, sin gráficos, sin dimensiones nuevas.

---

## 3 · Specific-Period Selector

- **Control:** un `<select>` nativo, igual que el de supervisor, colocado junto a
  las pestañas. Su etiqueta cambia con la pestaña: **Week**, **Month** o
  **Year**; nunca un genérico «Period».
- **Opciones:** las da el servidor (`periods`), de la más reciente a la más
  antigua:
  - empiezan en el **periodo en curso del servidor**;
  - retroceden hasta el **primer día con jornada** del alcance autorizado
    (tenant + supervisor elegido o todos);
  - con un tope: **52 semanas, 36 meses, 10 años**;
  - sin datos, sólo el periodo en curso.
- **Por qué acotado:** una lista sin límite crecería con la historia del tenant.
  Un periodo más antiguo sigue siendo consultable (`date`) y, si es el que se
  muestra —una recarga—, se añade a las opciones.
- **Identificador:** el inicio del periodo (`2026-09-14`), nunca la etiqueta.

## 4 · Week Behavior

Etiqueta `Oct 12–18, 2026`; la tarjeta izquierda agrupa **por día**; elegir un
día acota el desglose a ese día. La semana es lunes–domingo, la del explorador.

## 5 · Month Behavior

Etiqueta `October 2026`; agrupa **por semana**, recortada al mes (`Sep 1–6`,
… `Sep 28–30`), como Activity. Elegir una semana acota el desglose a esos días
del mes.

## 6 · Year Behavior

Etiqueta `2026`; agrupa **por mes**. Elegir un mes acota el desglose a ese mes.
Un mes sin datos del mismo año es un subgrupo válido y vacío.

---

## 7 · Interactive Temporal Groups

- Cada fila es un **botón** con `aria-pressed`: se elige con ratón, toque o
  teclado (Tab + Enter, probado).
- La fila elegida usa el patrón de elemento elegido del producto
  (`border-primary bg-primary/5`) **y** la marca de texto **Selected**: no
  depende sólo del color.
- Las filas tienen ≥ 44 px de alto en móvil (probado).
- La tarjeta sigue mostrando sólo los subgrupos con registros, como el V0.7. Un
  día con millas pero sin actividad (p. ej. sólo un regreso a casa) sí aparece
  y se puede elegir: muestra `0 activities`.

## 8 · Full-Period vs Subgroup State

Dos alcances separados:

| Alcance | Lo forman | Manda en |
|---|---|---|
| Periodo principal | supervisor + tipo + periodo concreto | KPIs, tarjeta izquierda, Excel, URL |
| Subgrupo | la fila elegida | sólo el *Activity Breakdown* |

Volver al periodo entero: botón **Whole week / month / year** en la cabecera de
la tarjeta, o volver a pulsar la fila elegida. No hace falta cambiar de pestaña
ni recargar.

## 9 · Activity Breakdown Filtering

- Sigue siendo **por propósito**: Client Visit, Employee Visit, Recruiting,
  Check Delivery, Office, Other.
- Con subgrupo, Miles, Time, Events y Est. cost son **sólo** de ese subgrupo; la
  tarjeta lo dice: *Showing Wed Sep 16 only*. Sin subgrupo: *Showing whole
  week*.
- Se calcula con **las mismas filas** que el resto del informe, acotadas por
  `session_date` con los mismos límites que la fila de la izquierda. Por eso el
  desglose del subgrupo (más lo excluido, como los regresos a casa) **concilia
  con su fila**: millas, tiempo, eventos y coste (prueba).
- Siguen las reglas de no duplicar: un viaje una vez, tramos no suman, varias
  actividades no multiplican.

## 10 · KPI Preservation

Los cuatro KPIs se calculan siempre con el periodo principal. Pruebas:

- API: la respuesta con `group` es **idéntica** a la del periodo entero en todo
  menos el desglose (`summary`, `groups`, `periods`, `fuel`…).
- Navegador: el texto de los cuatro KPIs se lee antes y después de elegir el
  subgrupo y **no cambia**, en Week, Month y Year.

## 11 · Supervisor / Period State Reset

| Cambio | Subgrupo | Periodo concreto | Probado |
|---|---|---|---|
| Supervisor | se borra | se conserva; sus opciones se recalculan para ese supervisor | E2E |
| Periodo concreto | se borra | el elegido | E2E |
| Pestaña (Week ↔ Month ↔ Year) | se borra | **el en curso del nuevo tipo**, que decide el servidor | E2E |
| Recarga | se borra (no se guarda) | se conserva desde la URL | E2E |

Al cambiar de tipo se vuelve al periodo en curso en vez de traducir el anterior
(p. ej. de una semana de septiembre al mes de septiembre): es lo que la
instrucción pide por defecto y evita anclas ambiguas en semanas que cruzan
meses.

---

## 12 · API / Read Model Changes

Sin un segundo modelo: se extiende el de RTE09.

`GET /api/reports`

| Parámetro | Antes | Ahora |
|---|---|---|
| `range` | week/month/year | igual |
| `date` | ancla (sólo pruebas) | ancla del periodo elegido; sin él, el en curso del servidor |
| `supervisor_user_id` | opcional | igual |
| `group` | — | **nuevo**: inicio de un día / semana / mes **del periodo**; si no lo es → **422** |

Respuesta, campos nuevos:

- `periods`: opciones del selector (`{start, end}`).
- `selected_group`: el subgrupo aplicado o `null`.

Con `group`, sólo cambian `breakdown`, `breakdown_excluded` y `activity_types`.

`GET /api/reports/export` **no** acepta `group`: si llega, se ignora (probado:
el archivo es idéntico).

Elegir un subgrupo hace **una** lectura más del informe del periodo, con
`group`; los KPIs y la tarjeta izquierda no se vuelven a pedir. Volver al
periodo entero no hace ninguna lectura.

---

## 13 · Desktop Evidence

Capturas locales en `var/screenshots/rte09-e01/` (fuera del repositorio):

- `escritorio-week-dia.png`:
  - semana *Sep 14–20, 2026* con el selector **Week** junto a las pestañas;
  - KPIs 17.0 · 0m · 3 · $0.00;
  - *Wed Sep 16* con la marca **SELECTED** y el botón *Whole week*;
  - desglose *Showing Wed Sep 16 only*: sólo **Office 3.0**.
- `escritorio-month-semana.png`: *September 2026*, *By week*, semana *Sep 14–20*
  elegida.
- `escritorio-year-mes.png`: *2026*, *By month*, *January* elegido: **Office
  7.0**.

### Los tres recorridos

```text
Week  Sep 14–20, 2026 → Wed Sep 16 → Breakdown: Office 3.0 mi       (KPIs 17.0 / 3 sin cambio)
Month September 2026  → Sep 14–20  → Breakdown: Client Visit 14.0 + Office 3.0
Year  2026            → January    → Breakdown: Office 7.0 mi       (KPIs del año sin cambio)
```

### Subgrupo cambia el desglose, no los KPIs, y el Excel sigue siendo el periodo

Con *Wed Sep 16* elegido:

- **Activity Breakdown**: sólo *Office 3.0*; *Client Visit* desaparece.
- **KPIs**: 17.0 · 0m · 3 · $0.00, idénticos a antes de elegir.
- **Excel descargado**: `…_2026-09-14_2026-09-20.xlsx` con **3 filas**, las de
  toda la semana (dos viajes del 15 y uno del 16), no la única del 16.

## 14 · Mobile Evidence

390 px, contexto táctil:

- Supervisor, pestañas y selector **Month / Week / Year** visibles, apilados.
- Un toque en una fila la elige; se ve la marca *Selected* y *Showing … only*.
- **Sin desbordamiento horizontal** al inicio, con día, semana y mes elegidos.
- Capturas: `movil-390-week-dia.png`, `movil-390-month-semana.png`,
  `movil-390-year-mes.png`.

## 15 · Export Regression

- El Excel de un periodo histórico elegido (agosto de 2026) contiene sólo ese
  mes y su nombre lo dice (`…_2026-08-01_2026-08-31.xlsx`).
- Con `group` en la petición, el archivo es **idéntico** al del periodo entero.
- Las 32 pruebas de RTE09 —16 columnas, conciliación, precio no inventado— siguen
  verdes.

## 16 · Security / Tenant Isolation

- Sin permisos nuevos: `route.reports.read` y `route.reports.export`.
- `group` sólo puede ser un subgrupo del periodo ya autorizado: cualquier otra
  fecha → 422, sin leer nada.
- Supervisor de otra compañía con `group`: el **mismo 404** que un id
  inexistente. Supervisor sin permiso con `group`: 403.
- Las opciones del selector no cuentan jornadas de otra compañía (prueba con
  datos de beta en 2024).

---

## 17 · Tests / Regression

**Nuevas — integración** `tests/integration/test_reports_historical.py`:
**24/24 PASS**.

**Nuevas — navegador** `tests/e2e/test_rte09_historical_breakdown_browser.py`:
**4/4 PASS** (escritorio con los tres recorridos y el Excel; reinicio del
subgrupo y recarga; reloj del navegador en 2024; móvil táctil).

**RTE09 existentes:** `test_reports.py` **32/32 PASS** con el código nuevo.

**Mutaciones** (§26):

| Protección quitada | Resultado |
|---|---|
| Filtro del subgrupo (el desglose ignora `group`) | **detectada**: 7 pruebas de integración fallan |
| KPIs recalculados con el subgrupo | **detectada**: 5 pruebas de integración fallan |
| Subgrupo conservado al cambiar supervisor, periodo o tipo | **detectada**: E2E `test_cambiar_el_contexto_borra_el_subgrupo…` |
| Fecha del navegador como autoridad (`new Date()` como ancla) | **detectada**: E2E `test_el_periodo_en_curso_lo_decide_el_servidor…` |

**4/4 detectadas.** Cada mutación de frontend se probó con su bundle
reconstruido; al terminar se restauraron los archivos y se reconstruyó el
bundle correcto (exit 0).

**Regresión:**

| Lote | Pruebas | PASS | FAIL | Omitidas | Exit |
|---|---|---|---|---|---|
| Suite completa, 3 workers (local) | 1359 | 1338 | 6 | 15 | 1 |

**Los 6 fallos son los mismos que antes de esta mejora** (`CONFIRMED` por su
nombre: idénticos a la regresión de RTE09) y no tocan Reports:

- `test_provisioning_alignment`: espera 12 capacidades del Administrador de
  Route y encuentra 16. Decisión de conteo pendiente desde antes de RTE09.
- 5 E2E de ubicación offline (`test_rte06_offline_durability`,
  `test_rte06_recovery_accuracy` ×4): pendientes de diagnóstico. Causa raíz
  `UNVERIFIED`.

Frente a la regresión de RTE09 (1327): +28 pruebas, las nuevas de esta mejora.

**Estáticos:** `npm run check` (typecheck + lint) exit 0 · `import app.main` OK
· bundle de producción reconstruido.

Fallos durante la ejecución (`CONFIRMED`), todos de las pruebas nuevas:

- La prueba del tope de opciones esperaba 52 semanas y obtuvo 1. **No es un
  defecto:** sin zona horaria, el «hoy» de un supervisor es su jornada más
  reciente (regla de T-1/T-2), y la única jornada de la prueba era de 2022. Se
  añadió una jornada de hoy a la prueba.
- Una prueba del «día sin actividad» no lo demostraba (dejaba el viaje con
  actividad en el mismo día). Se reescribió para que el día tenga sólo un
  regreso a casa.
- Lint: tres ternarios anidados, una línea larga y un `return` inconsistente.
  Corregidos.

---

## 18 · Expected → Implemented → Evidence → Gap

| # | Criterio (§25) | Estado | Evidencia | Gap |
|---|---|---|---|---|
| 1–2 | V0.7 conservado; pestañas presentes | VALIDATED | capturas | — |
| 3–6 | Selector; semana/mes/año con su etiqueta | VALIDATED | E2E (`label` Week/Month/Year; opciones `Sep 14–20, 2026`, `September 2026`, `2026`) | — |
| 7 | Periodos históricos | VALIDATED | E2E + `test_las_opciones_…` | — |
| 8 | Servidor manda la fecha | VALIDATED | E2E con reloj en 2024 + mutación | — |
| 9–11 | By day / week / month | VALIDATED | E2E | — |
| 12–15 | Filas interactivas; día, semana, mes | VALIDATED | E2E + 3 pruebas de API | — |
| 16–18 | Periodo entero por defecto; volver; selección visible | VALIDATED | E2E (`Whole …`, `aria-pressed`, *Selected*) | — |
| 19 | KPIs del periodo principal | VALIDATED | API idéntica salvo desglose; E2E; mutación | — |
| 20–22 | Supervisor, periodo y tipo borran el subgrupo | VALIDATED | E2E + mutación | — |
| 23–25 | Propósito; millas compartidas; sin duplicar | VALIDATED | conciliación por subgrupo; multi-actividad | — |
| 26 | Combustible sin cambios | VALIDATED | 32/32 RTE09; subgrupo en espera = 0 | — |
| 27 | Excel del periodo principal | VALIDATED | API + E2E | — |
| 28 | Tenant | VALIDATED | 404 idéntico; opciones sin beta | — |
| 29–31 | Escritorio, móvil, sin desbordamiento | VALIDATED | E2E + capturas | — |
| 32 | RTE09 sigue verde | VALIDATED | 32/32 | — |
| 33 | Pruebas discriminantes | VALIDATED | mutaciones | — |
| 34 | Sin Partial/Gap/Blocked sin explicar | VALIDATED | §19 | — |

---

## 19 · Remaining Issues

**Para CER (confirmación, no bugs):**

1. **Tope de opciones:** 52 semanas, 36 meses, 10 años. Si CER necesita más
   historia en el selector, es un número.
2. **Cambio de pestaña:** vuelve al periodo en curso del nuevo tipo, en vez de
   traducir el periodo anterior. Es el comportamiento por defecto de la
   instrucción.
3. **Días sin registros:** no aparecen como filas, igual que en el V0.7 y en
   Activity. Un día con millas pero sin actividad sí aparece.

**Heredado, fuera de esta mejora:**

4. Sin zona horaria configurada, el «periodo en curso» de un supervisor es el de
   su jornada más reciente (T-1/T-2). En producción las jornadas registran su
   zona y el caso no debería darse; se menciona porque explica el fallo de
   prueba del §17.
5. `test_provisioning_alignment` (12 frente a 16 capacidades) y los 5 E2E de
   ubicación offline siguen como estaban antes.

**Acción operativa:** ninguna. Sin migración, sin capacidades nuevas, sin
semillas. Basta con desplegar.

---

## 20 · Proposed Status

`RTE09 HISTORICAL PERIOD + INTERACTIVE BREAKDOWN COMPLETE / READY FOR CER VALIDATION`

---

## Estimación

**Esta mejora: 0 h restantes de desarrollo.** Queda la validación de CER.

| Componente | LoC | Coeficiente | Horas-agente |
|---|---|---|---|
| Backend (servicio, DAO, esquemas, router) | +142 / −15 | 150–200 LoC/h | 0,8 |
| Frontend (página, barra, tarjetas, entidad) | +362 / −88 | 50–70 LoC/h | 6,0 |
| Pruebas de integración | 384 | 80–100 LoC/h | 4,3 |
| E2E | 324 | 50–70 LoC/h | 5,4 |
| **Total** | **≈ 1210** | | **≈ 16,5** |

| Siguiente | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Ajustes tras la validación de CER | pendiente | desconocido | UI | 1–2 (+50 % de navegador → 1,5–3) |

---

## Git

| | |
|---|---|
| Rama | `feature/rte09-historical-period-breakdown` (desde `dev` `1ece5c7`) |
| Commits | `c3dee32` implementación, pruebas y este reporte · el siguiente añade este bloque |
| Push | sí |
| MR | **!86** · https://gitlab.com/cermanagementgroup/cermanagementgroup-route/-/merge_requests/86 → `dev` |
| Fusionado | **No**: pendiente de la validación de CER |
| Árbol | limpio tras el push |

---

## Siguiente paso

Revisión de CER y validación en campo. No se ha empezado ningún otro
checkpoint.
