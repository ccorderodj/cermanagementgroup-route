# CER Route · RTE08 · Activity personal del Supervisor / Executor

**Reporte de implementación** · 12 de octubre de 2026
**Instrucción:** `CER_ROUTE_RTE08_SUPERVISOR_EXECUTOR_ACTIVITY_IMPLEMENTATION_INSTRUCTIONS_V1_0.md`
**Rama:** `feature/rte08-personal-activity` · **Base:** `dev` en `5939a9e`

---

## Estado propuesto

`RTE08 PERSONAL ACTIVITY COMPLETE / READY FOR CER VALIDATION`

Propuesto, no declarado: **la certificación es de CER**. No se fusiona ni se
despliega sin autorización del PO.

---

## 1 · AS-BUILT verificado antes de cambiar código

| Pieza | Lo que había en `dev` (`5939a9e`) |
|---|---|
| Ruta personal | `/route/activity` (`RouteActivityPage`), protegida por `exige_ejecucion_de_ruta` → **`route.worksession.execute`**. Mostraba `NotBuiltYet` «The Activity Explorer is not built yet · RTE08» |
| Shell | `RouteMobileShell`: cabecera *CER Route · Activity*, barra inferior **My Route / Activity / Me**, columna `max-w-md` |
| Vista admin | `/admin/route/activity` → `RouteActivityExplorerPage` (toda la lógica en la página) |
| API admin | `GET /api/activity-explorer?range&date&supervisor_user_id`, **`route.activity.read`**, supervisor validado contra los elegibles (404 si no) |
| Dominio | `activityexplorer/dao.py`: `dia_actual_de`, `periodo`, `paradas_del_dia`, `agregados_por_dia`, `componer_grupos`; R-1 (`has_activity`) y H-2 integrados |
| Componentes | `ExplorerFilterBar` (con H-1), `ExplorerDaySummary`, `ExplorerActivityCards`, `ExplorerGroupList` |
| Capacidades | `supervisor` tiene `route.worksession.execute` y **no** `route.activity.read`; `route_admin` tiene las dos |
| T-1/T-2, AM/PM, H-1 | **Integrados** en `dev`; RTE08 los consume, no los reimplementa |

---

## 2 · Expected vs Implemented (AC01–AC12)

| AC | Estado | Evidencia |
|---|---|---|
| **AC01** sin placeholder, en el shell, pestaña activa | **Completed** | E2E: sin «is not built yet», `aria-current="page"` en Activity; capturas |
| **AC02** Day/Week/Month/Year y fecha | **Completed** | E2E: Year → mes → semana → día; escritorio con fecha; paridad en los 4 rangos |
| **AC03** equivalente al admin para esa persona | **Completed** | integración: respuesta **idéntica** salvo el directorio, en los 4 rangos; E2E: mismo resumen y mismas tarjetas que el admin |
| **AC04** sin selector ni otros usuarios | **Completed** | E2E móvil y escritorio: `#explorer-supervisor` ausente; API: `supervisors: []` |
| **AC05** sujeto fijado por el servidor; tenant | **Completed** | integración: 4 parámetros manipulados ignorados; administrador en `/me` ve lo suyo; beta no ve alpha |
| **AC06** supervisor ve lo suyo y no el admin | **Completed** | integración: `/me` 200 y explorador admin 403; sin cambios de RBAC |
| **AC07** viajes sin actividad, sin contarlos | **Completed** | integración R-1: el regreso a casa aparece con `has_activity=false`; `activities = 2` |
| **AC08** semántica de millas y estados | **Completed** | integración: parada en curso, millas pendientes sin cifra; dos jornadas el mismo día suman sin duplicar |
| **AC09** T-1/T-2 y AM/PM | **Completed** | mismo componente y mismo formato que el admin (capturas idénticas en contenido) |
| **AC10** My Route, Me, barra, sin overflow | **Completed** | E2E: ida y vuelta por la barra; 360/365/390/430 sin desbordar; el último bloque queda sobre la barra inferior |
| **AC11** admin, H-1 y permisos sin cambios | **Completed** | regresión: pruebas del explorador admin, H-1 y permisos verdes (§6) |
| **AC12** sin migraciones ni mutaciones | **Completed** | sin migración; integración: consultar en los 4 rangos no cambia ningún recuento ni `updated_at` |

---

## 3 · Reutilizado vs cambiado

**Backend**

- `app/routers_api/activityexplorer/router.py`:
  - la construcción de la vista se extrae a `_vista(...)`, **compartida**;
  - el endpoint admin la llama con el supervisor validado, sin cambio de
    contrato ni de permiso;
  - **nuevo** `GET /api/activity-explorer/me?range&date`.
- Mismas consultas del DAO, mismas reglas R-1 y H-2, mismo esquema
  `ExplorerView`. **Sin SQL nuevo.**

**Frontend**

- **Nuevo** `widgets/RouteActivityExplorer/ActivityExplorerPanel`: la lógica que
  vivía en la página admin —lectura vigente, ancla de fecha del servidor, bajada
  de nivel, estados de carga y error— con `scope="admin" | "self"`.
- `RouteActivityExplorerPage` (admin): cabecera + panel `admin`. Mismo marcado y
  mismo comportamiento.
- `RouteActivityPage` (personal): `RouteMobileShell` + panel `self`. Sustituye
  al marcador.
- `ExplorerFilterBar`: opción `showSupervisor` (por defecto `true`, el admin no
  cambia); en `self` es `false`.
- `fetchMyActivity` junto a `fetchExplorer`, validado con el mismo esquema Zod.

**Sin cambios:** capacidades, catálogo, semillas, migraciones, modelo de datos,
millas, Today, My Route, Me.

### Una diferencia de presentación, a propósito

En la vista **personal**, al cambiar de pestaña o de periodo, el periodo
anterior no se pinta bajo la pestaña nueva mientras llega la respuesta, ni si
falla (FR-02.4).

La vista **admin** conserva su comportamiento documentado: mantiene los datos
de la misma persona durante un fallo (FR-09 de RTE08 admin). Cambiarlo habría
alterado `/admin/route/activity`, que AC11 protege. Si CER quiere la misma regla
en el admin, es un ajuste de una línea.

---

## 4 · Aislamiento personal: cómo y con qué pruebas

**Diseño**

- **Sujeto:** `get_current_user` de la sesión. **Tenant:** `get_company_required`
  del subdominio.
- El endpoint **no declara** `supervisor_user_id`, `user_id`, `company_id` ni
  `tenant_id`. Si llegan, se **ignoran** y la respuesta es la misma que sin
  ellos (tratamiento elegido y probado).
- **Capacidad:** `route.worksession.execute`, la misma que abre el shell y
  ejecuta la jornada. **No hizo falta ninguna decisión RBAC**: es una capacidad
  personal que ya existía.
- `route.activity.read` sigue siendo sólo del explorador admin; el supervisor
  sigue sin tenerla (prueba sobre `DEFAULT_ROLES`).
- **Sin directorio:** `supervisors` va vacío; no viaja PII de otras personas.

**Pruebas de servidor**

| Caso | Resultado |
|---|---|
| Otro supervisor con viajes el mismo día | no aparece: 17.0 mi propias, no los 7.0 ajenos |
| `supervisor_user_id` / `user_id` / `company_id` / `tenant_id` manipulados | respuesta idéntica a la limpia |
| Administrador en `/me` con `supervisor_user_id` ajeno | ve **lo suyo** (7.0 mi); su ruta admin sigue con su alcance |
| Supervisor | `/me` 200 · explorador admin **403** |
| Sin sesión | 401 |
| Sin capacidad de ejecución (`viewer`) | 403 |
| Otro tenant | el supervisor de beta no ve nada de alpha; una cuenta de alpha no inicia sesión en beta |
| Sólo lectura | recuentos de jornadas, viajes, paradas y auditoría, y `max(updated_at)`, iguales antes y después |

---

## 5 · Capturas y comparación con el admin

Locales en `var/screenshots/rte08-personal/` (fuera del repositorio):

| Captura | Qué muestra |
|---|---|
| `movil-365-dia.png` | Shell de My Route; Day/Week/Month/Year **sin selector**; 17.0 mi · 0m · 2 · —; Client Visit, Home (sin actividad), Office; pestaña Activity activa |
| `movil-365-semana.png` | la semana con *Wed Sep 16* |
| `escritorio-propio-dia.png` | el mismo shell en escritorio: fecha sí, supervisor no |
| `escritorio-admin-mismo-dia.png` | `/admin/route/activity`, el admin elige al supervisor y el 16-sep |

**Comparación, 16 de septiembre de 2026, mismo supervisor**

| | Personal | Admin |
|---|---|---|
| Resumen | 17.0 mi · 0m · 2 · — | 17.0 mi · 0m · 2 · — |
| Tarjetas | Client Visit 10.0 · Home 4.0 · Office 3.0 | idénticas |

Nota de las capturas móviles de página completa: la barra inferior fija aparece
a media altura porque el navegador la dibuja en la posición de la ventana. La
prueba que importa —desplazada hasta el final, la última tarjeta queda **por
encima** de la barra— pasa.

---

## 6 · Pruebas y regresión

| Lote | Pruebas | Resultado |
|---|---|---|
| Integración `tests/integration/test_my_activity.py` | 18 | **18/18 PASS** |
| E2E `tests/e2e/test_rte08_personal_activity_browser.py` | 7 | **7/7 PASS** |
| Explorador admin `tests/integration/test_activity_explorer.py` tras el refactor | todas | **PASS** |
| `npm run check` (typecheck + lint) | — | exit 0 |
| Bundle de producción | — | reconstruido |
| Suite completa, 3 workers (local) | 1384 | 1362 PASS · 6 FAIL · 1 ERROR · 15 omitidas · exit 1 |
| Prueba del ERROR, repetida aislada | 1 | **PASS** |

**Ninguno de los 6 fallos ni el error es de RTE08:**

- `test_provisioning_alignment` (12 frente a 16 capacidades del Administrador de
  Route): ya fallaba antes; la decisión de conteo sigue pendiente. Esta
  instrucción dice expresamente que no autoriza tocar roles por él, y no se ha
  tocado.
- 5 E2E de ubicación offline (`test_rte06_offline_durability`,
  `test_rte06_recovery_accuracy` ×4): los mismos 5 que ya fallaban, pendientes
  de diagnóstico. Causa raíz `UNVERIFIED`.
- **1 ERROR** en `test_rte06_odometer_lifecycle_browser.py::test_the_start_reading_task_survives_the_camera_and_a_recreated_tab`:
  *«uvicorn no llegó a responder»* al **preparar** la prueba, sin llegar a
  ejecutarla. Repetida aislada: **PASS**. Causa `LIKELY`: el arranque del
  servidor de pruebas superó su tiempo de espera con la máquina cargada. No
  toca código de RTE08.

Las pruebas del explorador de administración, H-1, R-1, H-2, permisos, My Route
y el shell pasaron dentro de la suite completa.

**Fallos durante la ejecución, todos de las pruebas nuevas (`CONFIRMED`):**

- La comprobación entre tenants dio 200. El inicio de sesión de alpha en beta
  **había fallado**, y el cliente de prueba conservó la cookie anterior de beta.
  Con un cliente limpio, el inicio de sesión se rechaza y `/me` responde
  401/403. **No hubo fuga.**
- La comprobación «nada bajo la barra inferior» medía antes de que terminara el
  desplazamiento y sólo la cabecera de la tarjeta. Se cambió a desplazar hasta
  el final y medir la tarjeta completa.
- Lint: sangría tras envolver los campos de la barra. Corregida con
  `eslint --fix`.

**Dependencias:** T-1/T-2, AM/PM y H-1 están integrados en `dev`; RTE08 los
consume, no los reimplementa.

---

## 7 · MR, estado y riesgos

| | |
|---|---|
| Rama | `feature/rte08-personal-activity` (desde `dev` `5939a9e`) |
| Commits | `acac811` implementación, pruebas y este reporte · el siguiente añade este bloque |
| Push | sí |
| MR | **!87** · https://gitlab.com/cermanagementgroup/cermanagementgroup-route/-/merge_requests/87 → `dev` |
| Fusionado / desplegado | **No**: pendiente de validación de CER y autorización del PO |

**Hallazgo incidental, preexistente y también en el admin:** un viaje sin
actividad muestra su hora como `— · 11:43 PM UTC——`. El «UTC» es la regla
integrada para jornadas sin zona registrada; en las pruebas, las jornadas no
llevan zona. El `——` final es cómo se pinta un tramo sin final. Las dos vistas
son idénticas; RTE08 no lo cambia. **Si CER lo ve en campo, es un ajuste de
formato aparte.**

**Riesgos restantes**

- La navegación móvil entre días es la del explorador aprobado: pestañas y filas
  que bajan de nivel, **sin** campo de fecha en móvil (línea base y H-1). Para
  ver un día concreto en el teléfono hay que bajar desde Week, Month o Year.
- La diferencia de presentación entre personal y admin al cambiar de periodo
  está documentada en §3.

**Acción operativa:** ninguna. Sin migración, capacidades nuevas ni semillas.
Al desplegar, que los supervisores recarguen la aplicación.

---

## Estimación

| Componente | LoC | Coeficiente | Horas-agente |
|---|---|---|---|
| Backend (endpoint, refactor compartido) | +65 / −6 | 150–200 LoC/h | 0,4 |
| Frontend (panel compartido, páginas, barra, servicio) | ≈ +310 / −270 movidas | 50–70 LoC/h | 5,2 |
| Pruebas de integración | 245 | 80–100 LoC/h | 2,7 |
| E2E | 261 | 50–70 LoC/h | 4,4 |
| **Total** | **≈ 880** | | **≈ 12,7** |

**RTE08 personal: 0 h restantes de desarrollo.** Queda la validación de CER.

| Siguiente | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Ajustes tras la validación de CER | pendiente | desconocido | UI | 1–2 (+50 % de navegador → 1,5–3) |
