# CER Route · Jerarquía organizacional, roles, permisos y alcance de datos

**Reporte de implementación · Control A (preflight y diseño de contratos)** ·
13 de octubre de 2026
**Instrucción:** `CER_ROUTE_ROLE_HIERARCHY_RBAC_DATA_SCOPE_IMPLEMENTATION_INSTRUCTIONS_V1_0.md`
**Base:** `dev` en `153f9e6`

---

## Proposed Status

`ROLE HIERARCHY + RBAC + DATA SCOPE BLOCKED — CER DECISION REQUIRED`

El inventario encontró la situación que la propia instrucción manda elevar (§6 y
§16, Control A): **la administración delegada y la lectura por jerarquía
necesitan capacidades y una estrategia de asignación de privilegios que hoy no
existen.** Construir sin decidirlo obligaría a una de dos cosas que la
instrucción prohíbe:

- dar a CEO, COO y RM el rol `route_admin`, que lee y administra **todo el
  tenant** («permisos amplios por comodidad»); o
- inventar capacidades sin aprobación.

**No se ha escrito código de producto.** Todo lo que es diseño técnico queda
decidido en §4, para que con las respuestas el desarrollo (Control B) empiece
sin más preguntas. Este archivo se convertirá en el reporte final.

---

## 1 · AS-BUILT / CONFIRMED

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

## 2 · Decisiones de CER necesarias

### D-1 · ¿Con qué rol leen y administran CEO, COO y RM? · **bloquea el desarrollo**

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

### D-2 · ¿Qué puede administrar cada nivel? · **bloquea la administración delegada**

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

### D-3 · Tras un traslado, ¿quién ve la historia? · **no bloquea**; se aplica la opción restrictiva salvo indicación

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

### D-4 · Usuarios existentes sin cargo · **confirmación**

Tras el despliegue nadie tiene cargo ni superior. Consecuencias:

- Todos siguen ejecutando su jornada y viendo su Activity propia (AC11).
- El Superadmin sigue viendo todo el tenant.
- Un CEO, COO o RM **no ve a nadie** hasta que se le asignen subordinados.
- No se rellena ninguna jerarquía por inferencia (§4 y §9).

**Recomendación:** confirmar. La asignación inicial la hace el Superadmin desde
la pantalla de usuarios.

---

## 3 · Hallazgos de seguridad, fuera de esta instrucción

| # | Hallazgo | Severidad | Acción propuesta |
|---|---|---|---|
| S-1 | **Sin guarda sobre el objetivo**: un actor con `users.update/delete` puede suspender, editar o retirar a alguien de rol superior (p. ej. `route_admin` → `owner`). Sólo se impide retirarse a sí mismo | alta | dentro de este frente: la regla «nunca a tu nivel o superior» de D-2 lo cierra para Route |
| S-2 | Un `manager` del núcleo puede conceder `owner` por `/api/users` (ya documentado en `role_policy.py:45`) | alta | núcleo, fuera de alcance; decisión aparte |
| S-3 | Cualquiera con `roles.create` puede crear un rol `management`, que da autoridad de aprobación | media | núcleo, fuera de alcance |
| S-4 | `supervisores()` y `today_rows` **no** excluyen pertenencias suspendidas ni identidades desactivadas | media | se corrige al aplicar el alcance: la política única filtra pertenencia activa |
| S-5 | La pantalla Route Users lista, suspende y retira por `/api/users` (contrato del núcleo), no por `/api/route/users` | baja | se alinea al añadir cargo y superior |

---

## 4 · Diseño técnico, decidido (para Control B)

### 4.1 Modelo, aditivo

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

### 4.2 Política única de alcance

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

### 4.3 Pantallas

Sin páginas nuevas. En el formulario de usuarios de Route, dos campos:

- **Cargo**;
- **Superior**, con opciones del servidor ya filtradas por nivel y alcance.

OSM y Supervisor ven exactamente la misma experiencia de ejecución.

---

## 5 · Estimación de Control B + C (con D-1 A, D-2 tal cual, D-3 por periodo)

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

## 6 · Git

⟨GIT⟩

---

## 7 · Siguiente paso

Respuestas a **D-1 (con D-1b y D-1c), D-2 y D-4**; D-3 sólo si CER prefiere la
opción «vigente». Con ellas se ejecutan Control B y Control C, y este archivo
pasa a ser el informe final.
