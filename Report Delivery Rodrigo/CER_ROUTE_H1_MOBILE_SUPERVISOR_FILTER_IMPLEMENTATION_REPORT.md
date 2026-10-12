# CER Route · H-1 · Selector de supervisor en móvil (User Activity)

**12 de octubre de 2026**
**Instrucción:** `CER_ROUTE_H1_MOBILE_SUPERVISOR_FILTER_INSTRUCTIONS.md`
**Rama:** `fix/h1-mobile-supervisor-filter`

---

## Status

`PENDING VALIDATION`

Implementado y validado con E2E en cinco anchos, pruebas de seguridad y
regresión. Queda la **validación manual de CER en un teléfono real** con una
cuenta de administrador autorizada (§9 de la instrucción), que no puedo hacer.

---

## 1 · Base y AS-BUILT confirmado

| | |
|---|---|
| Rama base | `dev` en **`a8968f8`** (T-1/T-2 y AM/PM ya integrados: nada concurrente que aislar) |
| Página | `pages/RouteActivityExplorerPage/ui/RouteActivityExplorerPage.tsx` |
| Componente | `features/RouteActivityExplorer/ui/ExplorerFilterBar.tsx` |
| API | `GET /api/activity-explorer` (`range`, `date`, `supervisor_user_id`) |
| Guarda | `route.activity.read` en la página y en el endpoint |

**Confirmado en el código, `CONFIRMED`:**

- La página pasaba `showFields={!esMovil}`. **Ese interruptor ocultaba dos
  controles, no uno**: el selector de supervisor **y la fecha**. El
  diagnóstico previo sólo mencionaba el selector.
- El servidor valida `supervisor_user_id` contra los supervisores elegibles de
  la compañía (perfil activo y no borrado) y responde **404** a cualquier otro.
- Las opciones del selector las da el servidor, del tenant autenticado.

**Reproducido con el bundle anterior:** a 390 px el selector no existe en la
página.

---

## 2 · La corrección

### 2.1 · El selector, y sólo el selector

`ExplorerFilterBar`: el interruptor `showFields` se sustituye por `showDate`.
El selector se dibuja **siempre**; la fecha, sólo fuera de móvil, como en la
línea base. **Ningún otro control aparece en móvil** (FR1.6).

En móvil el selector ocupa el ancho de la barra (`w-full`); en escritorio,
`md:w-auto`, igual que antes. El punto de corte de `useIsMobile` es 768 px, el
mismo que `md:` de Tailwind.

**Escritorio, sin cambios — demostrado:** captura antes (bundle anterior) y
después, misma página y mismos datos, comparadas píxel a píxel:

```
barra de filtros   976×57     píxeles distintos: 0
página completa    1280×900   píxeles distintos: 0
```

### 2.2 · Un defecto que el selector en móvil habría hecho visible · FR2.6

Al cambiar de supervisor, la página **seguía pintando los datos del anterior**
mientras llegaba la nueva lectura. Y si la lectura del nuevo fallaba, el aviso
*«Showing the last known state»* presentaba como suyos los datos de la otra
persona, con el selector ya en el nuevo nombre. Es exactamente lo que prohíben
FR2.6 y el caso límite «red caída o selección rápida».

**Corrección mínima:** los datos sólo se pintan si su `supervisor_user_id` es el
seleccionado. Si no coinciden, la pantalla muestra el estado que ya existía para
eso: *Loading recorded activity…* o *Activity history could not be read*.
Cambiar la fecha o el rango **no** cuenta: siguen siendo los datos de la misma
persona, y conservarlos durante un fallo es lo que FR-09 ya pedía.

**Afecta también a escritorio**, porque es el mismo estado de la página. Es el
**único** cambio de comportamiento de H-1 y no altera la disposición (la
comparación de §2.1 es con datos ya cargados). Lo dejo explícito porque la
instrucción pide no cambiar escritorio: lo que cambia es que escritorio tampoco
enseña datos de otra persona durante un cambio.

### 2.3 · Archivos

| Archivo | Cambio |
|---|---|
| `features/RouteActivityExplorer/ui/ExplorerFilterBar.tsx` | `showFields` → `showDate`; selector siempre visible; ancho completo en móvil |
| `pages/RouteActivityExplorerPage/ui/RouteActivityExplorerPage.tsx` | `showDate={!esMovil}`; `vigentes` (§2.2) |
| `tests/integration/test_activity_explorer.py` | 3 pruebas de seguridad nuevas |
| `tests/e2e/test_h1_mobile_supervisor_filter_browser.py` | E2E nueva |
| `tests/e2e/test_rte08_activity_explorer_browser.py` | expectativa móvil actualizada a H-1 (§5.4) |

---

## 3 · Impacto

| | |
|---|---|
| API / contratos | **ninguno** |
| Esquema / migraciones | **ninguno** |
| Permisos / roles / semillas | **ninguno** |
| Reglas de negocio, métricas, kilometraje, zona horaria | **ninguno** |
| `/route/activity`, navegación inferior de My Route, menús | **sin tocar** |

---

## 4 · Seguridad, tenant y permisos

| Caso | Resultado | Evidencia |
|---|---|---|
| Sin sesión | **401** | `test_sin_sesion_no_se_explora` (nueva) |
| Sin `route.activity.read` (supervisor) | **403** | `test_sin_la_capacidad_no_se_explora` (existente) |
| Supervisor de otro tenant por id | **404** | `test_no_se_ve_el_supervisor_de_otro_tenant` (existente) |
| Otro tenant **frente a** id inexistente | **mismo estado y mismo cuerpo**, sin nombres | `test_otro_tenant_y_un_id_inexistente_son_indistinguibles` (nueva) |
| Designación retirada del mismo tenant | no aparece en el selector; manipulando el id, **404** | `test_un_supervisor_no_elegible_del_mismo_tenant_no_se_lee` (nueva) |
| Opciones del selector | sólo del tenant | `test_las_opciones_del_selector_son_del_tenant` (existente) |

El backend no cambió, así que **las tres nuevas también pasan con el código
anterior**: son guardas de seguridad que fijan el contrato que H-1 no puede
debilitar, no reproducciones del defecto. Mostrar el selector no concede nada:
la puerta sigue en el servidor.

---

## 5 · Validación

### 5.1 · E2E · `test_h1_mobile_supervisor_filter_browser.py` · 8/8 PASS

| Prueba | Comprueba |
|---|---|
| Elegir A y luego B en móvil | el selector se ve; la petición lleva el `supervisor_user_id` elegido; la respuesta devuelve ese mismo id; lo pintado es de esa persona; **nada de A queda bajo el nombre de B** (AC01, AC02) |
| Cambiar el rango tras elegir A | Week, Month y Year conservan A en la petición, en la respuesta y en el selector (AC03) |
| 360, 390 y 430 px, 844×390 apaisado y 1280 escritorio | selector dentro de la ventana, objetivo táctil ≥ 24 px, sin desbordamiento; **la fecha oculta en móvil y visible en escritorio** (AC03, AC09) |
| Fallo de red al cambiar a B | *Activity history could not be read*, **sin** datos de A, selector en B (FR2.6) |

Los dos supervisores son elegibles y con historias distinguibles el mismo día:
A visita *ABC Manufacturing*; B —el `route_admin`, que también hace trabajo de
campo, el caso límite del §7— vuelve a casa.

Capturas en `var/screenshots/h1/`: `movil-360`, `movil-390`, `movil-430`,
`movil-horizontal`, `escritorio`, `movil-390-supervisor-a`,
`movil-390-supervisor-b`, `movil-fallo-al-cambiar`, las barras recortadas de
cada ancho, y `antes/` y `despues/` de escritorio.

### 5.2 · Hallazgo incidental · 844 px apaisado · `CONFIRMED` preexistente

A 844 px la página ya usa la disposición de escritorio y **las pestañas de rango
sobresalen 10 px** del borde. Medido con el bundle **anterior** a H-1: idéntico
(`right=854`). Arreglarlo sería rediseñar esa disposición, fuera de H-1.

La E2E lo trata con precisión en vez de esconderlo: a 844 px exige que **lo
único que sobresale sean las pestañas preexistentes** y que el selector quepa
entero; en los demás anchos exige cero desbordamiento.

### 5.3 · Comprobaciones

```
npm run typecheck     0 errores
npm run lint:ts       0 errores
npm run build:prod    compilado (2 avisos de tamaño, preexistentes)
```

### 5.4 · Regresión

| Lote | Tests | PASS | Fallos | Exit | Duración |
|---|---|---|---|---|---|
| Sin navegador, 3 workers | 1117 | **1101** | 1 preexistente | 1 | 9 min 40 s |
| Navegador dirigido, 1.ª pasada | 31 | 30 | **1** | 1 | 7 min 24 s |
| `test_rte08…` tras actualizarla | 8 | **8** | 0 | 0 | 2 min |

- **Sin navegador:** 1101 = las 1098 de la última regresión de `dev` + las 3
  de seguridad nuevas. Único fallo, `test_provisioning_alignment` (14 frente a
  12), preexistente y fuera de H-1.
- **Navegador dirigido:** User Activity (RTE08), R-1, T-1/T-2, AM/PM, H-1,
  Today (RTE07) y H-2. Falló **una** prueba:
  `test_rte08 … el_movil_mantiene_la_jerarquia_y_oculta_los_campos`. Exigía
  que el selector **no** existiera en móvil: es la regla V0.7 que H-1 cambia
  por decisión del PO. Se actualizó con el patrón del proyecto —*old
  expectation / approved decision / new expectation*— y **sigue exigiendo la
  fecha oculta**. Tras eso, su archivo: 8/8.
- **No se ejecutó** la batería de navegador completa (≈ 1 h): el cambio es de
  una sola página, y todos los archivos de navegador que la tocan, o tocan
  Today, están arriba. `NOT RUN` para el resto; en la última ejecución completa
  sólo fallaban los 5 de ubicación sin conexión, ajenos.
- 15 omitidas, como siempre: el motor de rutas real no está configurado aquí.

---

## 6 · Acceptance Criteria

| AC | Estado | Evidencia |
|---|---|---|
| AC01 · selector visible y operable en móvil | **VALIDATED** | §5.1, 360/390/430 |
| AC02 · A o B envía el filtro correcto y pinta sus datos | **VALIDATED** | §5.1, petición/respuesta/pantalla |
| AC03 · rango y fecha; ningún control móvil no deseado | **VALIDATED** | §5.1; la fecha sigue oculta en móvil |
| AC04 · Today, totales y detalle intactos | **VALIDATED** | §5.4: Today, H-2, R-1 y RTE08 en verde |
| AC05 · sin sesión y sin permiso, bloqueados | **VALIDATED** | §4 |
| AC06 · otro tenant / no elegible, rechazo seguro | **VALIDATED** | §4 |
| AC07 · sólo cambia User Activity de administración | **VALIDATED** | §2.3 |
| AC08 · sin migraciones, reglas ni permisos | **VALIDATED** | §3 |
| AC09 · escritorio intacto; móvil sin desbordar | **VALIDATED** | 0 píxeles distintos; §5.1; 844 px en §5.2 |
| AC10 · `IN_PROGRESS` y H-2/R-1 intactos | **VALIDATED** | §5.4; ningún cambio de backend |

---

## 7 · Pendiente

| Elemento | Estado |
|---|---|
| Validación manual en un teléfono real, cuenta de administrador autorizada | **PENDING VALIDATION** — CER |
| Pestañas de rango a 844 px | hallazgo preexistente, **fuera de alcance** |
| `test_provisioning_alignment` (14 frente a 12) | preexistente, **fuera de H-1**, sin tocar |

---

## 8 · Estimación

| Tarea | Volumen | Complejidad | Horas-agente |
|---|---|---|---|
| Base y AS-BUILT | — | — | 0,4 |
| Barra y página (incluido FR2.6) | ~60 LoC | UI | 1,0 |
| Seguridad (3) | ~95 LoC | integración | 0,8 |
| E2E (8), antes/después de escritorio, diagnóstico de 844 px | ~330 LoC | navegador | 3,5 |
| Regresión, reporte y entrega | — | — | 1,3 |
| **Total** | **≈ 490 líneas** | | **≈ 7 h** |

---

## 9 · Git

`PENDIENTE`
