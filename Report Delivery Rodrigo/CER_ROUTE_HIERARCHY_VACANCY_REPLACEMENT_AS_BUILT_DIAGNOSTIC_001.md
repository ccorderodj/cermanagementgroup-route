# CER Route — Jerarquía ante cargos vacantes y reemplazos: diagnóstico AS-BUILT

**Reporte 001 — respuesta a** `CER_ROUTE_ORG_HIERARCHY_VACANCY_REPLACEMENT_DIAGNOSTIC_V1_0.md`
**Fecha:** 14 de octubre de 2026
**Estado:** **DIAGNÓSTICO ENTREGADO — GATE**. No se implementa nada hasta que el PO apruebe la arquitectura y las reglas de reemplazo. **La jerarquía no se declara certificada.**

---

## 0. Versión y entornos

| Elemento | Valor |
|---|---|
| Rama y commit | `dev` @ `20942dc` (incluye V1.3 `e5371b6`, MR !90) |
| Migración | `0018_route_distinct_roles` (base local y base de tests) |
| Frontend servido en local | `app/static/javascript/` compilado el 13-10-2026 a las 23:57 (-06:00). El trozo `284.js` contiene el formulario V1.3: `Reports to`, `allowed_parents`, `role_positions` y la condición de render idéntica al fuente |
| Reproducción | Base **de tests** (se crea y se vacía en cada ejecución), app ASGI real, Edge con Playwright y el **mismo bundle**. Los scripts son desechables y **no se añadieron al repositorio** |
| Base local `db-dev-cer-route` | Solo `SELECT` en transacción de solo lectura |
| Entorno desplegado | **NOT RUN**: sin acceso |

No se modificó código, esquema, datos, roles, capacidades ni configuración.

---

## 1. Reproducción y causa raíz del campo que desaparece

### 1.1 Lo que se reprodujo

Mismo estado que la base local: un COO con RM y Supervisor debajo, al que la pantalla general le cambia el rol a `supervisor`, de modo que el cargo sigue siendo COO.

| # | Pantalla | Estado | «Reports to» | Opciones | Evidencia |
|---|---|---|---|---|---|
| A | **CER Route → Users** → Edit | CEO presente; se elige **COO** | **Visible** | Solo CEOs | [A-route-users-coo-con-ceo.png](CER_ROUTE_HIERARCHY_VACANCY_REPLACEMENT_assets/A-route-users-coo-con-ceo.png) |
| A' | CER Route → Users → Edit | CEO presente; se elige Supervisor | Visible | CEOs y el RM fuera de su rama (los de su rama se excluyen: evita ciclos) | registro de la reproducción |
| B | **Access control → Users** → Edit | El mismo usuario; se elige **COO** o Supervisor | **No existe, para ningún rol** | — | [B-access-control-users-coo.png](CER_ROUTE_HIERARCHY_VACANCY_REPLACEMENT_assets/B-access-control-users-coo.png) |
| C | CER Route → Users → Edit | **CEO sin cargo vigente**; se elige COO | Visible, **vacío**, con «No eligible superior for this role yet.» | 0 | [C-route-users-coo-sin-ceo.png](CER_ROUTE_HIERARCHY_VACANCY_REPLACEMENT_assets/C-route-users-coo-sin-ceo.png) |
| C' | Igual que C, al guardar | — | El formulario **bloquea** con «Choose who this person reports to» y **no envía nada** | — | 0 peticiones PUT/POST |

- **Consola:** 0 errores en todos los estados.
- **Red:** `GET /api/route/organization/options?user_id=…` y `GET /api/route/users/assignable-roles` responden **200** con el contenido esperado.

### 1.2 Causa raíz

1. **CONFIRMED — el diálogo es el mismo componente en dos pantallas.** `SecurityUserForm` solo muestra «Reports to» con `contract === 'cer-route'` (`app/components/react/features/SecurityUsers/ui/SecurityUserForm.tsx:116`, condición en `:644`). En **Access control → Users** (`/admin/security/users/list`, `SecurityUsersPage` → `SecurityUsersPanel` sin `contract`) el campo **nunca** se pinta.
   - Título, descripción y orden de campos son **idénticos** en las dos pantallas; la única diferencia visible es la miga de pan.
   - La captura del PO (COO elegido y hueco a la derecha) coincide con el estado B. Que la tomara en esa pantalla es **LIKELY**: la captura no muestra la URL.
2. **CONFIRMED — en CER Route el campo no desaparece por elegir COO**, ni con datos equivalentes a los locales. **Lo que ocurre ahí sin CEO cargado es otra cosa:**
   - el campo aparece **vacío** con un aviso;
   - el formulario **impide guardar**, porque `PADRES_PERMITIDOS[coo] = {ceo}` (`app/routers_api/organization/models.py:82-93`);
   - el servidor también exige superior: «This role needs a superior», 422 (`organization/service.py:241-246`).

   **Hoy no se puede dar de alta ni reasignar un COO mientras no exista un CEO con cargo.**
3. **Se descarta un bundle desactualizado:** el bundle local contiene V1.3 (§0).

### 1.3 Hallazgos durante la reproducción

| # | Hallazgo | Evidencia | Estado |
|---|---|---|---|
| H-1 | **Desde Access control → Users se puede cambiar el rol de un jefe con equipo** (200) **sin tocar su cargo**: queda rol `supervisor` con cargo `coo`. Por CER Route la misma operación da **409**. Es lo que pasó en la base local el 14-10 entre las 15:51 y las 15:54 | Repro API; `usermanagement/router.py:245-248` (`sincroniza` solo en contexto o actor de Route) | **CONFIRMED** |
| H-2 | Al abrir Edit user en CER Route, «Reports to» **no precarga el superior vigente** (10 s de observación). Obliga a elegirlo otra vez para guardar: no hay pérdida de datos, pero sí una regresión de UX. El test V1.3 sí lo comprueba para Sales | [D-route-users-sin-precarga-superior.png](CER_ROUTE_HIERARCHY_VACANCY_REPLACEMENT_assets/D-route-users-sin-precarga-superior.png) | CONFIRMED; causa **UNVERIFIED** |
| H-3 | Con el CEO **suspendido**, la API de opciones **lo sigue ofreciendo** como superior, pero el servidor **rechaza** asignar bajo él (422 «must be an active member») | Repro API | **CONFIRMED** |
| H-4 | Puede haber **varios CEO** a la vez: 3 vigentes en la repro. No hay restricción de unicidad | Repro API; `org_assignment` sin índice por cargo | **CONFIRMED** |

---

## 2. Modelo AS-BUILT

**No existe una posición organizacional persistente independiente de la persona.** El organigrama es **persona → persona**. **CONFIRMED.**

| Pieza | Qué es | Dónde |
|---|---|---|
| `org_assignment` | Cargo y superior **de una persona** en un periodo `[valid_from, valid_to)`; `superior_user_id` apunta a **otra persona** | `organization/models.py:121-180` |
| Integridad en la base | Una abierta por persona y compañía (índice parcial `uq_org_assignment_current`); sin solapes (`EXCLUDE` gist); `valid_to > valid_from`; nadie es su propio superior; persona y superior **del mismo tenant** por FK compuesta a `user_company` (superior con `RESTRICT`) | `:126-168` |
| Integridad en el servicio (con candado por compañía) | El cargo sale del rol (`CARGO_DE_ROL`); el superior debe ser **miembro activo con cargo** y de un cargo de `PADRES_PERMITIDOS`; sin ciclos; quien tiene directos no pasa a un cargo del que ellos no puedan depender (409); retirar con directos da 409 | `organization/service.py:172-324, 388-434` |
| Unicidad de ocupantes | **Ninguna**: N CEO, N COO, N RM por tenant | H-4 |
| Rol ↔ cargo | Uno por rol: CEO, COO, Regional Manager, OSM, `supervisor`, Sales. `route_manager` es heredado. `route_admin` y los roles del núcleo quedan fuera del árbol | `organization/models.py:98-108` |
| Sincronización rol → cargo | `update_user` sincroniza **solo** si se envía superior o si el contexto o el actor son de Route | `usermanagement/router.py:226-274` |
| Alcance | CEO, COO, RM y `route_manager`: su rama por **periodos**, según `WorkSession.started_at` (D-3). Cualquier otro rol (también uno propio o sin rol de Route): **tenant** | `organization/scope.py:47, 74-137` |
| Delegación | Un manager solo gestiona su rama, cargos por debajo del suyo, Sales solo si es CEO; 404 fuera de su rama | `organization/delegation.py` |
| Auditoría | `audit_event` con `org_assignment` `assign`/`reassign`/`retire` y valores antes y después; rol en `user` `update` | `service.py:308-323` |

**Consecuencia:** «el puesto» solo existe mientras alguien lo ocupa. Si nadie lo ocupa, no hay nodo al que colgar a nadie.

---

## 3. Matriz de escenarios

| Caso | Esperado (negocio) | Implementado | Evidencia | Gap | Impacto |
|---|---|---|---|---|---|
| COO sin CEO ocupante | COO elegible; «Reports to» claro (pendiente o bloqueado) | Elegible; campo visible y vacío con aviso; guardar bloqueado (cliente y 422) | Estados C y C'; `service.py:241-246` | No se puede dar de alta un COO con el CEO vacante. El aviso no explica la causa («falta CEO») | **Alto** en arranque y en reemplazos |
| CEO **suspendido** (ausencia temporal) | La estructura se conserva; nadie hereda permisos | Suspender, 200; **todas las asignaciones se conservan** apuntando al CEO; el COO sigue viendo su rama; el CEO pierde el acceso | Repro API | Se ofrece al CEO suspendido como superior y luego se rechaza (H-3). Sales solo lo ve `route_admin`/owner mientras dure | Medio |
| CEO **sin cargo** (vacante real) | La estructura de COO, RM y Sales permanece | Los subordinados siguen apuntando a la persona; el CEO no aparece como candidato; no se puede colgar nada nuevo de él | Estado C | No hay nodo «CEO vacante» | Alto |
| Retirar o degradar CEO, COO o RM **con** equipo | Sin romper la estructura | **Por CER Route:** 409 «Reassign them first» (retirar y degradar). **Por el núcleo:** retirar, 409; **cambiar rol, 200 sin tocar el cargo** (H-1) | Repro API; base local | **Agujero en el contrato del núcleo** | **Alto**: ya ocurrió |
| Reemplazo **CEO-A → CEO-B** | Relaciones intactas; el saliente pierde autoridad y el entrante la gana desde su asignación | Posible **a mano**: alta de CEO-B, mover cada directo (incluido Sales) y luego degradar o retirar a CEO-A. Cada paso es atómico; **el conjunto, no** | Repro API (el mismo flujo con COO) | Sin operación de reemplazo: N pasos y ventanas con dos CEO | Medio-alto |
| Reemplazo **COO-A → COO-B** | La rama sigue sin exponerse a Sales; no se recrean usuarios ni jornadas | Mover RM-A y SUP-C a COO-B: 200 cada uno. COO-A ve 0 en Today; COO-B ve su rama. Degradar a COO-A sin equipo: 200. Historial: filas cerradas y abiertas, con auditoría `reassign` | Repro API | Igual: manual y uno a uno | Medio |
| RM sin ocupante | Los equipos siguen asociados a su posición | Solo si la persona sigue (suspendida). Si se retira, 409 hasta mover al equipo | Repro API | No existe «RM vacante» | Medio |
| Sales bajo CEO | Ningún COO o RM lo ve, por ninguna vía | Today, Activity, Reports y Excel: 404/excluido. Repro: COO-B pide Activity de Sales, **404** | `tests/integration/test_org_hierarchy.py:441-517, 659-688` + repro | Ninguno | — |
| Tenant A frente a B | Ningún cargo cruza tenants | FK compuesta a `user_company`; test de otro tenant | `models.py:136-147`; `test_org_hierarchy.py:290, 688` | Ninguno | — |
| Cambios concurrentes | Sin ciclos ni cruces; versionado y auditoría | Candado por compañía, versión, `EXCLUDE`, test de concurrencia | `service.py:199-202`; `test_org_hierarchy.py:420` | Ninguno | — |
| Historia tras reemplazo (D-3) | El sucesor ve desde su asignación, salvo decisión | Las ventanas salen de `org_assignment` por periodo; COO-B **lista** a su equipo en la semana. Que vea jornadas **anteriores** a su asignación depende de `started_at`: por diseño, no | `scope.py:74-137`; tests `:571-612` | Requiere decisión (DR-4) | — |

---

## 4. Alternativas

### A — Persona → persona (actual), con reemplazo transaccional

**Qué añade:**
- **una operación «Replace occupant»**: en una transacción y con el candado existente, mueve los directos de A a B, ajusta los roles de A y B y deja un evento por movimiento con un `replacement_id` común;
- **el cierre de H-1**: el contrato del núcleo rechaza (409) un cambio de rol que contradiga la jerarquía, o lo sincroniza;
- **la corrección de H-2 y H-3** y un aviso explícito: «No CEO assigned yet — assign a CEO first».

| Criterio | Valoración |
|---|---|
| Ventajas | Cambio pequeño; reutiliza tablas, constraints, alcance, delegación y tests; no migra datos |
| Vacantes | **No las modela.** Una ausencia temporal se cubre suspendiendo (ya conserva la estructura). Una vacante prolongada **bloquea** altas debajo de ella, o exige un ocupante interino |
| Riesgo | Bajo. El reemplazo mueve N filas en una transacción |
| Migración / rollback | Sin migración de esquema; rollback = revertir el código |
| APIs / frontend | 1 endpoint nuevo (`POST /api/route/organization/{user_id}/replace`); ajustes en `update_user` del núcleo y en `SecurityUserForm` |
| Historia | Intacta (periodos), atribuida por `started_at` |
| Esfuerzo | **11–15 h-agente** (ver §7) |

### B — Puestos estables + ocupación temporal

**Qué introduce:**
- una tabla `org_position` (tenant, tipo, `parent_position_id`) con plazas múltiples;
- una tabla `org_occupancy` (posición, usuario, periodo);
- la plaza vacante no concede nada; el alcance se calcula por la **ocupación vigente**.

| Criterio | Valoración |
|---|---|
| Ventajas | Vacantes y reemplazos naturales (cambia el ocupante, no las relaciones); altas bajo una plaza vacante posibles; organigrama legible sin personas |
| Riesgo | **Alto.** Reescribe `scope.py` (ventanas por periodo de ocupación), `delegation.py`, opciones, formulario, Today, Activity, Reports y Excel, y la migración de cada `org_assignment` a plaza + ocupación conservando la historia. Toda la batería de tests de jerarquía y alcance debe rehacerse |
| Migración / rollback | Migración de datos con interpretación (una plaza por persona actual; la historia a ocupaciones). Rollback posible pero costoso; requiere documentar la interpretación (AGENTS, migraciones §6) |
| Seguridad | La autorización pasa a ser **rol + ocupación vigente**. Bien hecho es más claro; mal hecho, una plaza mal enlazada da alcance a quien no debe |
| Esfuerzo | **38–55 h-agente** |

### C — Mecanismo existente equivalente

**No existe.** No hay ningún concepto de plaza, puesto o nodo en el código, la base ni las migraciones 0001–0018. Lo más cercano es la **suspensión**, que ya mantiene la estructura durante una ausencia temporal (§3). Cubre «ausencia temporal», no «vacante».

### Recomendación

**A, con las tres correcciones**, si CER acepta que **una plaza sin ocupante no admite altas nuevas debajo** (DR-1). Cubre:
- ausencia temporal (suspensión);
- reemplazo atómico CEO, COO y RM;
- el agujero H-1, que ya produjo el incidente de hoy;

y lo hace con el riesgo más bajo.

**B solo si** CER necesita **vacantes prolongadas con gente colgando y altas bajo la plaza vacante**, o un organigrama de plazas independiente de las personas. En ese caso se recomienda hacer **primero A** (cierra H-1 y da el reemplazo) y B como frente aparte.

---

## 5. Decisiones de CER

- **DR-1 Vacantes.** ¿Se permite dar de alta o reasignar personas bajo un cargo **sin ocupante**? Si **no**, basta A. Si **sí**, hace falta B.
- **DR-2 Número de CEO.** Hoy no hay límite (H-4). ¿Uno por tenant (restricción en la base) o varios?
- **DR-3 Quién autoriza un reemplazo.** ¿Solo Superadmin Route/owner? ¿Un CEO para su COO o RM? ¿Con aprobación de dos personas?
- **DR-4 Historia del sucesor.** Por defecto (D-3) el entrante **no** ve jornadas anteriores a su asignación y el saliente conserva las de su periodo. ¿Se mantiene?
- **DR-5 Pantalla general.** Para personas de la jerarquía, ¿Access control → Users **rechaza** el cambio de rol (recomendado: 409 con «Use CER Route → Users») o lo **sincroniza**?
- **DR-6 Ausencia temporal.** ¿Se confirma «suspender» como la forma de ausencia temporal (la estructura se conserva y nadie hereda permisos)?

---

## 6. UX mínima en Edit user (sin mockups)

1. **Rol** siempre visible y seleccionable (ya es así).
2. **«Reports to» siempre visible** en CER Route cuando el rol tiene cargo, con tres estados explícitos:
   - con candidatos → la lista, **precargada con el superior vigente** (corrige H-2);
   - **sin ocupante del cargo superior** → «No CEO assigned yet. Assign a CEO first.» (según DR-1: bloqueado o pendiente);
   - **superior suspendido** → no se ofrece; aviso «Current superior is suspended».
3. **En Access control → Users**, para personas de la jerarquía: el rol de Route se muestra **en solo lectura** con «Managed in CER Route → Users», o el servidor responde 409 (DR-5). Así nunca vuelve a parecer que el campo «desaparece».
4. **Reemplazo**: una acción «Replace…» en la fila del jefe (CER Route → Users), con un paso de confirmación que lista a quién se mueve. No hace falta una página nueva.

Se separan rol (capacidades), cargo (sale del rol), ocupante (la persona) y superior (otra persona). No se añaden campos a la operación diaria.

---

## 7. Plan de pruebas posterior y esfuerzo (opción A)

| Bloque | Pruebas | Horas-agente |
|---|---|---|
| H-1: el contrato del núcleo no rompe la jerarquía | Integración: owner, admin y manager por `/api/users` → 409 o sincronizado; roles del núcleo sin cargo intactos; regresión del contrato del núcleo | 1,5–2 |
| Reemplazo transaccional | Unitarias del servicio; integración CEO→CEO (con Sales), COO→COO, RM→RM; fallo a mitad → nada cambia; concurrencia (dos reemplazos simultáneos); auditoría con `replacement_id`; tenant cruzado → 404 | 4–5 |
| Alcance tras reemplazo | Today, Activity, Reports y Excel: saliente sin alcance, entrante con alcance desde su asignación; COO nuevo nunca ve Sales (también por id); historia por `started_at` | 2–3 |
| H-2 / H-3 / avisos de vacante | Opciones sin suspendidos; precarga del superior; estados del campo | 1–1,5 |
| Web y móvil (E2E) | Edit user en los tres estados; reemplazo desde la fila; pantalla general con aviso o 409; capturas | 2–3 |
| **Subtotal** | | **10,5–14,5** |
| Margen | +10 % backend determinista; +50 % sobre la parte de navegador | **≈ 13–18** |

**Opción B (orientativo):**
- **Estimación:** 38–55 h-agente; con márgenes, ≈ 45–65.
- **Contenido:** modelo y migración con interpretación, más reescritura de alcance, delegación, formulario y la batería completa de jerarquía.

---

## 8. Estado de la base local (solo lectura, para contexto)

En `db-dev-cer-route`, la estructura sigue cargada (7 asignaciones vigentes), pero:
- 5 jefes tienen rol `supervisor` con cargo COO/RM/Sales, por H-1;
- el rol CEO tiene 27 capacidades;
- el usuario `test` alternó entre `admin` y `COO` por la pantalla general (sin cargo).

**Acción operativa** (no ejecutada): restaurar los roles desde **CER Route → Users**. Ver el diagnóstico de jerarquía anterior.

---

## 9. Gate

Entregado el diagnóstico. **Se detiene aquí** a la espera de:
- la aprobación del PO sobre la arquitectura (A o B);
- las decisiones DR-1 a DR-6.

La jerarquía **no** se considera certificada mientras H-1 siga abierto y un cargo vacante impida administrar relaciones de forma segura.
