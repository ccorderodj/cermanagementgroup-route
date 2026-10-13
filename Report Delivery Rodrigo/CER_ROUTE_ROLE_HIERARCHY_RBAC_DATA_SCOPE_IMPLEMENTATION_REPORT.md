# CER Route · Jerarquía organizacional, roles, permisos y alcance de datos

**Informe final · Control B (implementación) + Control C (pruebas y entrega)** ·
13 de octubre de 2026
**Instrucción ejecutada:** `CER_ROUTE_ROLE_HIERARCHY_SINGLE_DEVELOPMENT_INSTRUCTION_V1_1.md`
(única fuente; decisiones D-1 a D-4 cerradas)
**Base:** `dev` en `8dae58b` · **Rama:** `feature/role-hierarchy-rbac-scope`
**Control A** (preflight y decisiones, MR !88, documental): conservado como
**Anexo A**, sin borrar su evidencia. MR !88 **no** es implementación.

---

## Proposed Status

`ROLE HIERARCHY + RBAC + DATA SCOPE COMPLETE / READY FOR CER VALIDATION`

Propuesto, no declarado: **la certificación es de CER**. No se fusiona ni se
despliega sin su autorización expresa.

**La condición de seguridad de D-1 se cumplió**:
- `users.read/create/update` se conceden a `route_manager` **porque** la única
  API que las exige (`usermanagement`, montada en `/api/users` y en
  `/api/route/users`) quedó acotada a la rama en **todas** sus rutas.
- Esto se demostró con pruebas de API directa por ambos montajes (§4).
- No fue necesario bloquear ninguna pieza ni crear capacidades nuevas.

---

## 1 · AS-BUILT real (implementado)

| Pieza | Qué se construyó | Dónde |
|---|---|---|
| Modelo | `org_assignment`: cargo y superior por periodo `[valid_from, valid_to)`, autor, motivo, `version` | `app/routers_api/organization/models.py` |
| Migración | `0017_org_hierarchy`: tabla + restricciones + rol `route_manager` **vacío** en cada compañía. Sin backfill (D-4) | `app/migrations/versions/0017_org_hierarchy.py` |
| Garantías en la base | una asignación abierta por persona (índice único parcial) · sin solapes (`EXCLUDE … tstzrange && `) · periodo no vacío · nadie es su propio superior · persona y superior de **la misma compañía** (FK compuestas a `user_company`) | `org_assignment` |
| Servicio | asignar / reasignar / retirar con **candado por compañía** (`pg_advisory_xact_lock`): nivel estrictamente superior, sin ciclos, sin bajar a quien tiene subordinados, `ensure_version` (409), reloj de la base, auditoría | `organization/service.py` |
| Política de alcance | **una** función, `alcance_administrativo`: tenant (cualquier actor que no sea `route_manager`, contrato vigente) · rama vigente (Today) · rama **por periodo** con `WorkSession.started_at` (historia) · vacío | `organization/scope.py` |
| Delegación | quién gestiona a quién, qué cargos y roles asigna, bajo qué superior | `organization/delegation.py` |
| API nueva | `GET/PUT/DELETE /api/route/organization[/{user_id}]`, `GET …/options` (`users.read` / `users.update` + delegación) | `organization/router.py` |
| Rol | `route_manager` en el catálogo: 9 capacidades **existentes** | `app/core/rbac/catalog.py` |
| Today | rama vigente; además excluye pertenencias suspendidas/retiradas e identidades inactivas (B2.4) | `live/dao.py`, `live/router.py` |
| Activity admin | conjunto y jornadas acotados por periodo | `activityexplorer/router.py`, `dao.py` |
| Reports y Excel | mismo alcance, antes de agregar | `reports/router.py`, `service.py`, `dao.py` |
| Usuarios | listas, edición, acceso, readmisión, alta y baja pasan por la delegación | `usermanagement/router.py`, `dao.py`, `schemas.py` |
| Pantalla | **Position** y **Reports to** en el formulario existente de Users de Route; sin páginas ni menús nuevos | `features/SecurityUsers/ui/SecurityUserForm.tsx`, `entities/RouteOrganization` |

**Lo que no cambió:**
- capacidades de `route_admin` (16);
- `supervisor` (2);
- My Route, Activity personal, jornada, viajes, millas, T-1/T-2;
- el Core transversal (`app/core`), salvo el catálogo, donde se declara el rol.

---

## 2 · Matriz final cargo → rol → capacidades → alcance

| Cargo (nivel) | Rol | Capacidades | Alcance administrativo | Activity personal |
|---|---|---|---|---|
| Superadmin (no es eslabón) | `route_admin` | 16, **sin cambios** | **Tenant** (contrato vigente) | propia |
| CEO (4) | `route_manager` | ejecutar jornada, leer listas, Today, Activity, Reports, Excel, `users.read/create/update` | **su rama** | propia |
| COO (3) | `route_manager` | ídem | su rama | propia |
| Regional Manager (2) | `route_manager` | ídem | su rama | propia |
| OSM (1) | `supervisor` | ejecutar jornada, leer listas | **ninguno** | propia |
| Supervisor (1) | `supervisor` | ídem | ninguno | propia |
| Sin cargo | según su rol | según su rol | `route_manager` sin cargo: **nadie** | propia |

**OSM = Supervisor**, demostrado:
- mismo rol y mismo conjunto de permisos en la base y en la cookie `user_data`;
- mismas pantallas (todas las de administración responden 403 a los dos);
- la misma Activity propia.

### Delegación efectiva

| Actor | Gestiona a | Cargos que asigna | Rol que asigna | Superior posible |
|---|---|---|---|---|
| `route_admin` | cualquiera del tenant | todos | roles de Route (contrato vigente) | cualquiera de nivel mayor |
| CEO | descendientes vigentes con rol `supervisor` o `route_manager` | COO, RM, OSM, Supervisor | `route_manager` (COO, RM) · `supervisor` (OSM, Supervisor) | él o su rama |
| COO | ídem | RM, OSM, Supervisor | ídem | él o su rama |
| RM | ídem | OSM, Supervisor | `supervisor` | él o su rama |
| OSM, Supervisor | **nadie** | — | — | — |

**Reglas para todos:**
- nadie actúa sobre sí mismo;
- un manager nunca actúa sobre pares, superiores, ramas ajenas u otro tenant;
- un manager nunca actúa sobre un `route_admin` colocado en su rama (cerraría el
  acceso a su contraseña);
- un manager nunca asigna `route_admin` ni roles del núcleo;
- sin `users.delete`, un manager suspende pero no retira.

---

## 3 · Expected → Implemented → Evidence → Gap → Impact

| AC | Estado | Implementado | Evidencia | Gap / Impacto |
|---|---|---|---|---|
| **AC-01** `route_manager` sin tenant-wide; `route_admin` intacto | **COMPLETED** | rol con 9 capacidades; alcance de rama | `test_route_manager_tiene_exactamente_lo_aprobado`; 16 de `route_admin` sin tocar | — |
| **AC-02** CEO/COO/RM sólo su rama | **COMPLETED** | política única en Today, Activity, Reports, Excel, Usuarios | `test_today_por_rama_vigente`, `test_activity_por_rama_y_404_fuera`, `test_reports_y_excel_con_el_mismo_alcance`; E2E Today por cargo (5) | — |
| **AC-03** OSM = Supervisor | **COMPLETED** | mismo rol | `test_osm_y_supervisor_son_iguales`; E2E permisos idénticos | — |
| **AC-04** niveles opcionales, superior único, sin lateral/ciclos, tenant | **COMPLETED** | base + servicio con candado | `test_niveles_opcionales…`, `test_relaciones_invalidas…` (5), `test_superior_de_otro_tenant…`, `test_la_base_rechaza…`, `test_dos_reasignaciones_simultaneas_una_gana`; migración ida-vuelta | — |
| **AC-05** delegación por nivel, sin self-action ni escalamiento | **COMPLETED** | `organization.delegation` | `test_alta_delegada` (11 casos), `test_el_manager_no_escala_un_rol` (3), `test_nadie_se_asigna_a_si_mismo`, `test_un_route_admin_en_la_rama_no_es_gestionable` | — |
| **AC-06** ninguna ruta de usuarios elude la política | **COMPLETED** | guardas en cada endpoint de ambos montajes | §4 (matriz) | — |
| **AC-07** traslado RM-A → RM-B por `started_at` | **COMPLETED** | ventanas por periodo | `test_traslado_rm_a_rm_b_por_started_at` (incluye jornada nocturna que cruza T), `test_mover_una_rama_entera`, `test_historia_anterior_a_la_relacion_no_se_expone` | — |
| **AC-08** Reports = Excel en alcance | **COMPLETED** | mismo `construir` con el alcance | `test_reports_y_excel_con_el_mismo_alcance` (filas del Excel = pantalla; 404 por id ajeno en los dos) | — |
| **AC-09** sin cargo: Activity propia; manager sin subordinados: nada | **COMPLETED** | vacío ≠ todo | `test_un_manager_sin_cargo_no_ve_a_nadie`; RTE08 personal verde | — |
| **AC-10** traslado, revocación, suspensión sin alcance obsoleto | **COMPLETED** | sin caché; cálculo por petición | `test_el_cambio_rige_en_la_siguiente_lectura`, `test_suspendido_sale_de_today_y_su_historia_queda`, auditoría en `test_reasignar…` | — |
| **AC-11** vistas separadas, sin rediseño | **COMPLETED** | dos controles en el formulario existente | E2E menús, `/route/activity` sin selector, capturas | — |
| **AC-12** seguridad y regresión | **COMPLETED** | — | §6: suite completa + lote de verificación | 6 fallos previos ajenos al frente (§6) |

---

## 4 · Matriz de rutas administrativas × actor × objetivo

Todas probadas por **API directa**. «Rama» = descendiente vigente gestionable.

| Ruta | `route_manager` sobre su rama | … fuera de su rama, par, superior, sí mismo, `route_admin`, `owner` | … otro tenant | OSM / Supervisor |
|---|---|---|---|---|
| `GET /api/users/pagination` | sólo su rama; `count` también | — (no aparecen) | — | 403 |
| `GET /api/route/users/pagination` | ídem | — | — | 403 |
| `PUT /api/users/{id}` · `/api/route/users/{id}` | 200 | **404** | **404** | 403 |
| `PUT …/{id}` con `role_id` = `route_admin` / `route_manager` (si no es su cargo) / `owner` | **403** | — | — | 403 |
| `PUT …/{id}/access` (suspender/reactivar) | 200 (incluido reactivar a un suspendido) | **404** | **404** | 403 |
| `POST /api/route/users` (alta) | 200 con cargo y superior de su rama | **403** fuera de nivel, rama o rol; nada se crea | — | 403 |
| `POST …/{id}/reenrollment` | — | **404** (retirado ya no es de ninguna rama) | — | 403 |
| `DELETE …/{id}` | **403** (sin `users.delete`) | 403 | 403 | 403 |
| `GET /api/route/organization[/options]` | su rama; cargos por debajo del suyo | — | — | 403 |
| `PUT /api/route/organization/{id}` | 200 dentro de nivel y rama | **404** objetivo · **403** cargo/superior · **422** estructura | **404** | 403 |
| `GET /api/live/today` | rama vigente | — | — | 403 |
| `GET /api/activity-explorer` | rama por periodo | **404** idéntico a un id inexistente | 404 | 403 |
| `GET /api/reports` · `/export` | rama por periodo | **404** | 404 | 403 |
| `GET /api/supervisors/candidates` | **403** (exige `route.vehicles.read`, que no tiene) | — | — | 403 |

Páginas que exigen `users.read` (`/admin/route/users`, `/admin/security/users`):
un manager entra, pero sus datos salen del mismo router acotado. El menú no es
la protección.

---

## 5 · Migración, historial y traslados

**Migración** — en la base de pruebas aislada (`MODE=TEST`), nunca en la local
de desarrollo ni en producción:

| Paso | Resultado |
|---|---|
| `alembic heads` | **un** head: `0017_org_hierarchy` |
| `upgrade head` → `downgrade -1` → `upgrade head` | OK los tres |
| `alembic check` | «No new upgrade operations detected» |

- **Reversión:** borra la tabla y los roles `route_manager`. Si alguien ya tiene
  ese rol, la bajada se detiene (FK `RESTRICT`) en vez de dejarlo sin rol;
  documentado en el docstring.
- **Sin backfill:** tras la subida no hay ninguna asignación (prueba).

**Historia por periodo (D-3).**
- Reasignar cierra la fila vigente en el instante de la transacción y abre la
  nueva desde ese mismo instante: contiguas, sin hueco ni solape (prueba).
- La `version` sube en cada cambio.

Casos probados:

- **RM-A → RM-B en T.** Una jornada del 14, otra que empieza la noche del 15
  antes de T y termina tras T, y otra del 17:
  - RM-A ve **13 mi** (las dos primeras, la nocturna entera);
  - RM-B ve **5 mi** (la tercera);
  - en Today sólo RM-B lo tiene.
- **Rama entera:** RM-A pasa del COO al CEO en T.
  - El COO conserva lo anterior a T (10 mi) y pierde lo posterior.
  - El CEO ve las dos (15 mi).
- **Relación anterior desconocida:** un supervisor con jornadas previas
  asignado hoy a RM-A → RM-A ve **0**; el Superadmin, 9 mi.
- **Las jornadas no se tocan:** mismo recuento antes y después.

**Auditoría.**
- Cada asignación, reasignación y retirada escribe `audit_event`
  (`entity_type = "org_assignment"`) con actor, compañía, instante, valores
  anterior y nuevo y motivo.
- La baja de una pertenencia cierra su cargo, auditado con motivo
  «membership removed».

---

## 6 · Pruebas y regresión

| Lote | Pruebas | Resultado |
|---|---|---|
| Integración + seguridad `tests/integration/test_org_hierarchy.py` | 60 | **60/60 PASS** |
| E2E `tests/e2e/test_org_hierarchy_browser.py` (CEO, COO, RM-A, RM-B, OSM, Supervisor, Superadmin; escritorio y móvil) | 8 | **8/8 PASS** |
| Superficies afectadas (Activity, Today, Reports, Activity propia, usuarios, readmisión, permisos, cableado) | — | verdes salvo el fallo previo de abajo |
| `npm run check` (typecheck + lint) | — | exit 0 |
| Bundle de producción | — | reconstruido |
| Suite completa, 3 workers (local), 2.ª ejecución | 1453 | 1421 PASS · 16 FAIL · 1 ERROR · 15 omitidas · exit 1 |
| Verificación tras corregir: las 10 pruebas de «dos roles», `test_route_access_model`, `test_route_notes_migration_safety` y el resto de esos archivos | 115 | **115/115 PASS** |

**Clasificación de los 17 de la suite completa** (`CONFIRMED` por su
mensaje):

| Grupo | Pruebas | Causa | Estado |
|---|---|---|---|
| Previos, ajenos al frente | 6: `test_provisioning_alignment` (12 vs 16) y los 5 E2E de ubicación offline | ya fallaban antes de este frente | sin tocar; la causa raíz de los offline sigue `UNVERIFIED` |
| Fijaban «exactamente dos roles» | 10: `test_route_product_context` ×5, `test_route_admin_configuration` ×1, `test_route_access_browser` ×4 | D-1 aprueba el tercer rol; además, los 4 E2E localizaban el selector de rol como «el último desplegable», que ahora es *Reports to* | actualizadas: tres roles y 7 en el catálogo del núcleo, selector por id; conservan lo que protegen. **PASS** |
| Entorno | 1 ERROR: `test_route_notes_migration_safety::test_m4` | la base de prueba de ese worker tenía una revisión de Alembic **ajena al repositorio** (`925db8990bcf`): otro proceso de la máquina usa las mismas bases de prueba (ya ocurrió con `f5c5fde65b15`) | repetida aislada: **PASS** |

**Primera ejecución de la suite**, detenida al 44 %: ~213 errores de arranque
en pruebas de navegador («uvicorn no llegó a responder»).
- Esas mismas pruebas pasan sueltas.
- En la segunda ejecución, desde un estado limpio, no aparecieron.
- Causa `UNVERIFIED`; la más probable es la carga de la máquina durante el
  arranque del servidor de pruebas.

No se repitió la suite entera tras la verificación. El único cambio de
producto posterior es la etiqueta («Route Manager», fallo 5 de abajo), y las pruebas que la tocan están
en las 115.

### Fallos durante la ejecución, todos corregidos (`CONFIRMED`)

1. **Defecto de producto:** un manager que suspendía a un subordinado **no
   podía reactivarlo**. El rol se buscaba sólo con la pertenencia activa, y el
   suspendido salía de su rama.
   - **Corrección:** un suspendido sigue en su rama; uno retirado, no. El
     superior sigue teniendo que estar activo.
2. **Defecto de producto:** el formulario **se reiniciaba** al llegar las
   opciones de cargo y borraba lo ya escrito; el envío no salía.
   - **Corrección:** al llegar, sólo se rellenan Cargo y Superior.
   - Lo destapó el E2E del alta.
3. **Tres pruebas de RTE02 fijaban «exactamente dos roles de producto»**
   (`test_route_access_model` ×2, `test_route_role_authority`).
   - D-1 aprueba el tercero; se actualizaron a tres conservando su propósito:
     el formulario de Route sólo ofrece roles de Route, nunca del núcleo.
4. **Expectativas de prueba propias:**
   - OSM como superior de OSM responde **422** (estructura), no 403;
   - readmitir a un subordinado que sigue activo responde 409, que es inocuo;
     el caso real (un retirado) responde 404;
   - etiqueta del menú «Users», no «Route Users»;
   - espera a que lleguen las opciones antes de leerlas.
5. **Defecto de producto: choque de etiquetas.**
   - Al rol `route_manager` se le había puesto la etiqueta «Manager», que es
     como se ve en pantalla el rol `manager` **del núcleo**: en el formulario
     de Route las dos se confundirían.
   - Lo detectó la prueba que impide ofrecer roles del núcleo en Route.
   - **Corrección:** la etiqueta pasa a **«Route Manager»**; el código técnico
     no cambia.
   - Error propio por el camino: el reemplazo de la etiqueta alcanzó también la
     lista de roles del núcleo prohibidos de esa prueba. Lo delató la propia
     prueba y se devolvió a su valor.
6. **Herramienta:** dos scripts de edición se cortaron a medias. Uno lo hizo
   por una búsqueda de texto ambigua y el otro por un salto de línea mal
   escapado. Se completaron revisando el diff; ningún archivo quedó a medias.

---

## 7 · No regresión: OSM/Supervisor, Activity, exportaciones

- **OSM y Supervisor:** mismos permisos y misma Activity propia; 403 en Today,
  Activity admin, Reports, Users y organización (integración y E2E).
- **Activity personal** (`/api/activity-explorer/me`):
  - sin cambios; las 18 pruebas de RTE08 siguen verdes;
  - un manager en `/me` ve **lo suyo**, no su rama.
- **Exportación:** el Excel usa el mismo alcance que la pantalla (filas = cifras)
  y el mismo 404 para un supervisor fuera de alcance.
- **Superadmin:** Today, Activity y Reports siguen viendo todo el tenant,
  incluidos los que no tienen cargo.

---

## 8 · Riesgos, deuda y decisiones evitadas

**Decisiones no autorizadas que se evitaron:**
- Ninguna capacidad nueva.
- Sin equivalencias nuevas entre `owner`, `admin`, `manager` y `route_admin`:
  sólo `route_manager` se acota y todo lo demás conserva su contrato.
- `route_admin` sin tocar.
- `test_provisioning_alignment` sin maquillar.
- Sin backfill.

**Hallazgos fuera del frente, documentados y no tocados:**
- **S-2:** un `manager` del núcleo puede conceder `owner` por `/api/users`.
- **S-3:** cualquiera con `roles.create` crea roles `management` con autoridad
  de aprobación.

**Límites y deuda:**

1. **Los supervisores necesitan perfil** (`/admin/route/supervisors`, del
   Superadmin) para aparecer en Today, Activity y Reports.
   - Un RM puede crear un Supervisor en su rama, pero no su perfil ni su
     vehículo: no tiene `route.vehicles.*`.
   - Si CER quiere que lo haga, sería una delegación nueva.
2. **El Superadmin decide su propia visibilidad por rol, no por cargo.** Un
   `route_admin` con cargo de CEO sigue viendo el tenant entero. Es la regla
   «Superadmin no es eslabón».
3. **Un manager no aparece en su propio Today ni en su Activity admin**: ve a
   sus descendientes. Lo suyo, en `/route/activity`.
4. **Día inicial del explorador:** para un supervisor que salió de la rama, la
   vista abre en su último día de jornada, que puede caer fuera del periodo
   visible. Muestra vacío, no datos.
5. **La lista de Users enseña el código técnico del rol** («Route_manager»),
   como ya hacía con «Route_admin». Es un ajuste de presentación aparte.

**Acción operativa al desplegar** (no la hace el trabajo local):

1. Migración `0017` (aditiva).
2. *Converge* / `align_role_capabilities`, para dar sus 9 capacidades a
   `route_manager` en los tenants existentes; la migración lo crea vacío.
3. El Superadmin carga la estructura: cargo y superior de cada persona, y el
   rol `route_manager` a CEO, COO y RM.
4. Que todos recarguen la aplicación.

---

## 9 · Git

| | |
|---|---|
| Rama | `feature/role-hierarchy-rbac-scope` (desde `dev` `8dae58b`) |
| Commits | `a83dc96` implementación, pruebas y este informe · el siguiente añade este bloque |
| Push | sí |
| MR de código | **!89** · https://gitlab.com/cermanagementgroup/cermanagementgroup-route/-/merge_requests/89 → `dev` |
| MR documental previo | **!88** (Control A): sólo preflight y decisiones; **no** es implementación |
| Fusionado / desplegado | **No**: pendiente de certificación de CER |

---

## Estimación

**Este frente: 0 h restantes de desarrollo.** Queda la certificación de CER.

| Componente | LoC | Coeficiente | Horas-agente |
|---|---|---|---|
| Backend nuevo (`organization/`, migración) | ≈ 1130 | 150–200 LoC/h | 6,5 |
| Backend modificado (usuarios, Today, Activity, Reports, catálogo) | ≈ 270 | 150–200 LoC/h | 1,5 |
| Frontend (entidad + formulario) | ≈ 255 | 50–70 LoC/h | 4,3 |
| Pruebas de integración y seguridad | ≈ 680 | 80–100 LoC/h | 7,6 |
| E2E | ≈ 240 | 50–70 LoC/h | 4,0 |
| **Total** | **≈ 2575** | | **≈ 24 h** |

Frente a las 37 h base (48 con margen) del Control A.

| Siguiente | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Ajustes tras la validación de CER | pendiente | desconocido | dominio + UI | 2–4 (+30 % → 2,6–5,2) |

---

## Siguiente paso

Certificación de CER sobre el MR. Tras ella, el despliegue con las cuatro
acciones operativas del §8. **No se fusiona ni se despliega sin autorización.**

---

## Anexo A · Control A (13/10/2026) — evidencia inicial, sin cambios

Preflight y puerta de decisión entregados en MR !88. Su estado era `BLOCKED —
CER DECISION REQUIRED`; las decisiones D-1 a D-4 llegaron en la instrucción
V1.1 y este informe recoge su implementación. Se conserva tal cual como
evidencia.

### A.1 · AS-BUILT / CONFIRMED

| Pieza | Estado real en `dev` | Referencia |
|---|---|---|
| Jerarquía, cargo, superior | **No existe.** Ninguna columna `reports_to`, `manager_id`, `position`, `job_title` ni nivel en ningún modelo ni migración | grep sobre `app/` y `app/migrations/` |
| Usuario | `Users` (`user`): identidad global, sin relaciones | `users/models.py:8` |
| Pertenencia | `UserCompany`: **un rol por pertenencia** y una pertenencia por (usuario, compañía) | `companies/models.py:59`, `uq_user_company_user_company` |
| Roles | por compañía; `category` = `management` / `operative`, que **sólo** decide quién aprueba cambios de permisos; **no es un rango** | `roles/models.py:30` |
| Perfil de supervisor | `SupervisorProfile`, creado aparte por `POST /api/supervisors`; no ligado al rol | `vehicles/models.py:127` |
| Roles de producto Route | **dos**: `supervisor` y `route_admin`. El contrato `/api/route/users` sólo acepta esos dos | `catalog.py:327`, `role_policy.py:90-106` |
| `supervisor` | `route.worksession.execute`, `route.standardvalues.read` (2) | `catalog.py` |
| `route_admin` | **16**: usuarios (`read/create/update/delete`), vehículos, listas, ajustes de odómetro, ejecución, `route.live.read`, `route.activity.read`, `route.reports.read`, `route.reports.export` | `catalog.py` |
| Guarda de escalamiento | sólo una lista de roles asignables (`ROUTE_PRODUCT_ROLES`). **Sin rango, nivel ni «delegable»** | `role_policy.py:106` |
| Alcance de Today | todos los perfiles activos de la compañía | `live/dao.py:81-110` (el docstring anuncia que aquí se estrechará con jerarquía) |
| Alcance de Activity admin | `supervisores(company_id)`: todos los perfiles activos | `activityexplorer/dao.py:142-176` |
| Alcance de Reports y Excel | el mismo `supervisores(company_id)` | `reports/router.py:33-43`, `service.py:114` |
| Activity propia | `GET /api/activity-explorer/me`, sujeto de la sesión (RTE08) | `activityexplorer/router.py:106` |
| Permisos por petición | `get_user_permissions` se **recalcula en cada petición**: no hay caché de permisos que pueda quedar obsoleta | `users/permissions.py:30` |
| Menú | `user_data` + `requiredPermission` en `navigation.ts`; experiencia, no control | `useVisibleNavigation.ts:20` |
| Auditoría | `record_event(company_id, entity_type, entity_id, action, actor_user_id, summary, changes, reason)` sobre `audit_event` append-only | `core/audit/service.py:91` |
| Concurrencia | `ensure_version` (409) y `transaction()` | `core/dao/concurrency.py:31`, `core/db/session.py:95` |
| Migraciones | **un solo head**: `0016_rte09_reports_fuel` | `app/migrations/versions/` |
| `test_provisioning_alignment` | espera **12** capacidades de `route_admin`; el catálogo concede **16**. Sigue fallando; **no se toca** | `tests/integration/test_provisioning_alignment.py:306` |

**Consecuencia directa.** Hoy **ningún** rol permite leer Today, Activity o
Reports sin alcance de compañía completa. CEO, COO y RM no tienen cómo existir
en el sistema sin una decisión de capacidades.

---

### A.2 · Decisiones de CER necesarias

#### D-1 · ¿Con qué rol leen y administran CEO, COO y RM? · **bloquea el desarrollo**

**Hecho.** Sólo hay dos roles de producto. `supervisor` no lee nada
administrativo; `route_admin` lo lee y administra todo el tenant.

**Impacto.** Es lo que decide si un RM ve sólo su rama o la compañía entera.

| Opción | Cómo | A favor | En contra |
|---|---|---|---|
| **A** · Tercer rol de producto `route_manager` | Capacidades existentes, sin crear ninguna: `route.worksession.execute`, `route.standardvalues.read`, `route.live.read`, `route.activity.read`, `route.reports.read`, `route.reports.export`, `users.read`, `users.create`, `users.update`. **Alcance: sus subordinados.** CEO, COO y RM usan este rol; el cargo distingue el nivel | ninguna capacidad nueva; el menú ya funciona con las existentes; `route_admin` no cambia | el contrato `/api/route/users` pasa de 2 a 3 roles asignables (cambio de FR-01/FR-05 de RTE02) |
| B · CEO, COO y RM con `route_admin`, alcance recortado por cargo | `route_admin` con cargo → subordinados; sin cargo → tenant | sin rol nuevo | **cambia el significado de `route_admin`** y le deja vehículos, listas y ajustes de odómetro; es justo el «permiso amplio» que §6 prohíbe |
| C · Una capacidad por nivel | `route.org.ceo`, `route.org.coo`… | explícito | crea capacidades que codifican cargos; duplica el cargo |

**Recomendación: A.** Sin capacidades nuevas, `route_admin` intacto y el cargo
como única fuente del nivel.

**Sub-decisión D-1b · Excel.** ¿`route.reports.export` para `route_manager`?
**Recomiendo sí**: el Excel se filtra con el mismo alcance que la pantalla.

**Sub-decisión D-1c · Borrar usuarios.** ¿`users.delete` para `route_manager`?
**Recomiendo no** en esta etapa: un RM suspende el acceso (`users.update`) y la
baja la hace el Superadmin.

#### D-2 · ¿Qué puede administrar cada nivel? · **bloquea la administración delegada**

**Hecho.** No hay rango ni noción de «delegable»; además, hoy **ninguna guarda
impide actuar sobre alguien de rol superior** (por ejemplo, un `route_admin`
puede suspender o editar a un `owner`).

**Propuesta mínima**, que se valida **en el servidor** en cada operación:

| Actor | Puede crear / editar / suspender | Cargos que puede asignar | Roles que puede asignar |
|---|---|---|---|
| Superadmin (`route_admin`) | cualquier usuario de Route del tenant | todos | `route_manager`, `supervisor` (y `route_admin`, como hoy) |
| CEO | sólo a sus descendientes | COO, RM, OSM, Supervisor | `route_manager` (para COO/RM), `supervisor` (para OSM/Supervisor) |
| COO | sólo a sus descendientes | RM, OSM, Supervisor | ídem |
| RM | sólo a sus descendientes | OSM, Supervisor | `supervisor` |
| OSM, Supervisor | **nadie** | — | — |

Reglas comunes:

- nunca a sí mismo;
- nunca a su nivel o superior;
- nunca `route_admin`;
- nunca fuera de su rama ni de la compañía.

Un usuario nuevo creado por un manager queda **bajo** él o bajo un descendiente
suyo.

**Recomendación:** aprobar esta tabla tal cual.

#### D-3 · Tras un traslado, ¿quién ve la historia? · **no bloquea**; se aplica la opción restrictiva salvo indicación

**Hecho.** §9 lo deja expresamente sin decidir.

| Opción | Qué ve el RM-B después de recibir a un supervisor de RM-A | Riesgo |
|---|---|---|
| **Vigente** | toda la historia del supervisor, incluida la de cuando era de RM-A | **exposición nueva**: RM-B ve meses que nunca supervisó |
| **Por periodo de relación** | sólo las jornadas desde que el supervisor es suyo; RM-A conserva lo de su periodo | más complejo de explicar; dos RM ven partes distintas de la misma persona |

**Recomendación: por periodo de relación.** Es la opción restrictiva que §9
pide aplicar mientras no haya decisión, y es la que se implementará si CER no
indica otra cosa: cada relación guarda desde/hasta, y Activity, Reports y el
Excel filtran por `session_date` dentro de ese periodo. Today, que es «ahora»,
usa la relación vigente.

#### D-4 · Usuarios existentes sin cargo · **confirmación**

Tras el despliegue nadie tiene cargo ni superior. Consecuencias:

- Todos siguen ejecutando su jornada y viendo su Activity propia (AC11).
- El Superadmin sigue viendo todo el tenant.
- Un CEO, COO o RM **no ve a nadie** hasta que se le asignen subordinados.
- No se rellena ninguna jerarquía por inferencia (§4 y §9).

**Recomendación:** confirmar. La asignación inicial la hace el Superadmin desde
la pantalla de usuarios.

---

### A.3 · Hallazgos de seguridad, fuera de esta instrucción

| # | Hallazgo | Severidad | Acción propuesta |
|---|---|---|---|
| S-1 | **Sin guarda sobre el objetivo**: un actor con `users.update/delete` puede suspender, editar o retirar a alguien de rol superior (p. ej. `route_admin` → `owner`). Sólo se impide retirarse a sí mismo | alta | dentro de este frente: la regla «nunca a tu nivel o superior» de D-2 lo cierra para Route |
| S-2 | Un `manager` del núcleo puede conceder `owner` por `/api/users` (ya documentado en `role_policy.py:45`) | alta | núcleo, fuera de alcance; decisión aparte |
| S-3 | Cualquiera con `roles.create` puede crear un rol `management`, que da autoridad de aprobación | media | núcleo, fuera de alcance |
| S-4 | `supervisores()` y `today_rows` **no** excluyen pertenencias suspendidas ni identidades desactivadas | media | se corrige al aplicar el alcance: la política única filtra pertenencia activa |
| S-5 | La pantalla Route Users lista, suspende y retira por `/api/users` (contrato del núcleo), no por `/api/route/users` | baja | se alinea al añadir cargo y superior |

---

### A.4 · Diseño técnico, decidido (para Control B)

#### 4.1 Modelo, aditivo

Tabla nueva `org_assignment`: el cargo y el superior de una persona en una
compañía, con su historia.

| Columna | Regla |
|---|---|
| `company_id`, `user_id` | FK compuesta a `user_company`: no hay cargo sin pertenencia |
| `position` | `StrEnum` + `CHECK`: `ceo`, `coo`, `regional_manager`, `osm`, `supervisor` |
| `superior_user_id` | nullable (raíz); FK compuesta a `user_company` de **la misma compañía** |
| `valid_from`, `valid_to` | `valid_to` nulo = vigente |
| `created_by`, `version` | auditoría y concurrencia |

**Restricciones en la base:**

- **una asignación vigente por persona y compañía** (índice único parcial
  `WHERE valid_to IS NULL`);
- `superior_user_id <> user_id`;
- la FK compuesta impide superiores de otra compañía.

**Reglas en el servicio**, dentro de `transaction()` con bloqueo de fila:

- nivel del superior **estrictamente mayor**;
- **sin ciclos**: se recorre la cadena del superior propuesto;
- sin vínculos laterales OSM↔Supervisor (mismo nivel).

Cambiar de cargo o superior **cierra** la fila vigente y abre otra: la historia
queda para D-3. Cada cambio se audita (`record_event`, `entity_type =
"org_assignment"`, valores anterior y nuevo).

Niveles: CEO 4, COO 3, RM 2, OSM 1, Supervisor 1. **OSM y Supervisor comparten
nivel**: ni uno manda sobre el otro.

#### 4.2 Política única de alcance

`app/core/rbac/scope.py` (dominio de acceso de Route):

```text
alcance(actor, compañía, acción) →
  Superadmin (route_admin, owner, admin) → tenant
  con cargo de mando + capacidad de lectura  → descendientes (por periodo, D-3)
  cualquier otro                              → vacío en vistas de administración
/route/* → siempre el propio usuario (no pasa por aquí)
```

Se calcula **en cada petición** desde la base: sin caché, así que un cambio de
superior rige en la siguiente consulta (AC10). Filtra **antes de agregar**.

Superficies a las que se aplica, con la misma función:

- Today: `today_rows`.
- Activity: `supervisores()` y validación del supervisor pedido.
- Reports y Excel: `_supervisor_autorizado` y `construir`.
- Usuarios: lista, edición, acceso y baja por `/api/route/users`.

Un id fuera de alcance responde **404**, como hoy entre compañías.

#### 4.3 Pantallas

Sin páginas nuevas. En el formulario de usuarios de Route, dos campos:

- **Cargo**;
- **Superior**, con opciones del servidor ya filtradas por nivel y alcance.

OSM y Supervisor ven exactamente la misma experiencia de ejecución.

---

### A.5 · Estimación de Control B + C (con D-1 A, D-2 tal cual, D-3 por periodo)

| Bloque | Volumen | Complejidad | Horas-agente |
|---|---|---|---|
| Modelo, migración, invariantes, auditoría | ~450 LoC | dominio | 2,6 |
| Política de alcance + Today, Activity, Reports, Excel | ~350 LoC | dominio | 2,0 |
| Administración delegada y guardas (D-2, S-1, S-4) | ~400 LoC | dominio | 2,3 |
| Formulario: cargo y superior | ~250 LoC | UI | 4,2 |
| Pruebas de integración y seguridad (§13) | ~1300 LoC | integración | 14,5 |
| E2E: 5 cargos, 2 ramas, escritorio y móvil | ~500 LoC | navegador | 8,3 |
| Certificación, evidencia, reporte | — | — | 3,0 |
| **Subtotal** | **≈ 3250 LoC** | | **36,9** |
| **Con margen** (+10 % dominio · +30 % integración · +50 % navegador) | | | **≈ 48 h** |

D-3 «vigente» en vez de «por periodo» ahorraría unas 3 h.

---

### A.6 · Git

| | |
|---|---|
| Rama | `docs/hierarchy-rbac-control-a` (desde `dev` `153f9e6`) |
| Cambio | este reporte y la instrucción; **ningún código** |
| Commit | `606255d` · el siguiente añade este bloque |
| MR | **!88** · https://gitlab.com/cermanagementgroup/cermanagementgroup-route/-/merge_requests/88 → `dev` |
| Fusionado | **No** |

---

