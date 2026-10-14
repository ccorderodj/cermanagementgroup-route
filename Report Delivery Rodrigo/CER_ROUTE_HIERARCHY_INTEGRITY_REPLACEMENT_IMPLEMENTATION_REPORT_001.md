# CER Route — Jerarquía V1.4: integridad, retiro ascendente y sustitución de responsables

**Reporte de implementación 001 — respuesta a** `CER_ROUTE_HIERARCHY_INTEGRITY_REPLACEMENT_SINGLE_INSTRUCTION_V1_4.md`
**Fecha:** 14 de octubre de 2026
**Status: COMPLETED WITH PENDING VALIDATION.**
- **Lo que está terminado:** implementación y validación técnica en local, en la base de tests.
- **Lo que falta:** la certificación del PO, el despliegue y la regularización de datos de los entornos existentes.
- **Hallazgo crítico abierto:** el rol CEO tiene 27 capacidades en la base local (§3.3). **Bloquea la certificación.**

---

## 1. Base, rama y entornos

| Elemento | Valor |
|---|---|
| Base | `dev` @ `91f6513` (incluye V1.3 y los dos diagnósticos) |
| Rama / MR | `feature/hierarchy-integrity-replacement`; MR indicado en la sección Git del mensaje de entrega. **No fusionado ni desplegado** |
| Migración nueva | `0019_org_single_ceo` (head único: `alembic heads` → 1) |
| Base de tests | Se crea y vacía en cada ejecución; ahí se migró, se probó y se ejecutó todo |
| Base local `db-dev-cer-route` | **Sigue en la 0018.** Solo se consultó en modo lectura. **No se migró a propósito:** tiene 5 incoherencias rol/cargo, y la instrucción (§6) bloquea migrar un tenant con datos incoherentes hasta regularizarlo |
| Entorno desplegado | **NOT RUN**: sin acceso |
| Diferencias con el diagnóstico | Ninguna en el código de partida. Dos vías adicionales de incoherencia encontradas durante la implementación y cerradas: **readmisión** y **renombrar/borrar roles de Route** (§4.1) |

---

## 2. Qué se implementó y por qué

| Pieza | Qué hace | Por qué |
|---|---|---|
| `organization/contract_guard.py` | Por el contrato general (`/api/users`) responde **409** `managed_in_cer_route` a: cambiar el rol de quien tiene cargo; dar un rol de la jerarquía (CEO … Sales, Supervisor incluido) en alta, edición o readmisión; enviar `superior_user_id`. Se evalúa **antes de escribir** y **después de la delegación** (una escalada sigue dando 403) | H-1 / DR-5: un solo camino para la jerarquía. Lógica de Route; el núcleo solo la invoca |
| `usermanagement/router.py` | Llama a la guarda en alta, edición y readmisión. La **readmisión** por CER Route con un rol de la jerarquía exige superior y asigna el cargo en la misma transacción | La readmisión dejaba un rol de mando sin cargo: una vía de H-1 que no estaba en el diagnóstico |
| `roles/router.py` | 409 al **renombrar o borrar** los roles de CER Route (CEO, COO, Regional Manager, OSM, `supervisor`, Sales, `route_admin`, `route_manager`). La descripción y las capacidades siguen editables | El cargo **y el alcance** se deducen del nombre. Renombrar «COO» dejaba a todos los COO sin cargo y **con alcance de compañía entera**. Es una guarda puntual en el núcleo, con la lista leída del catálogo existente |
| Migración `0019` + `OrgAssignment` | Índice único parcial `uq_org_assignment_one_ceo (company_id) WHERE position='ceo' AND valid_to IS NULL`. Su *preflight* **se detiene sin cambios** si una compañía tiene más de un CEO y dice cuál; no elige a nadie. Tiene bajada | H-4 / FR-02: la unicidad garantizada también en concurrencia |
| `organization/service.py` | `asignar`: 409 «This company already has a CEO… use Replace manager». `pertenencias()`: rol y estado de cada miembro | H-4 con un mensaje que dice qué hacer |
| `organization/router.py` `/options` | Ya no ofrece superiores suspendidos | H-3 |
| `organization/succession.py` | **Retirar** (los directos suben al superior inmediato) y **Sustituir** (el sucesor ocupa el cargo bajo el mismo superior y recibe a todos los directos). Calcula la **estructura final**, la valida entera (padres permitidos, superior activo, sin ciclos, un CEO, directos que caben bajo el nuevo cargo), y la aplica en **una transacción**, con el candado de la jerarquía y **un único instante T**. Quien sale deja la compañía con la baja existente. Auditoría correlacionada por `operation_id` | FR-03 / FR-04 |
| `GET /api/route/organization/{id}/succession`, `POST …/retire`, `POST …/replace` (`dry_run`) | Vista previa y ejecución con el mismo cálculo. **Solo `route_admin` del tenant** (403 al resto, también a owner, admin y CEO); 404 si es de otro tenant | Decisión de mínimo privilegio (§2 de la instrucción) |
| `SecurityUserForm.tsx` | **H-2:** el selector ignora el valor vacío que emitía al montarse o al cambiar de opciones y que borraba el superior precargado. Sin candidatos: «No CEO assigned yet — assign a CEO first.» (u otro según el cargo). Superior vigente no disponible: aviso. En la pantalla general, el 409 se muestra **en el campo de rol** (por código, no por texto). La readmisión envía el superior | FR-06.1–06.4 |
| `SuccessionDialog.tsx` + menú de fila | «Replace manager…» / «Retire manager…» en **CER Route → Users**, solo para `route_admin` y filas CEO/COO/RM. Vista previa del servidor (quién pasa a qué cargo, a quién se mueve cada uno, quién sale), motivo opcional y confirmación. Escritorio y móvil | FR-06.5 |
| `app/db/scripts/hierarchy_preflight.py` | Inventario de **solo lectura**: CEO múltiples, rol ≠ cargo, rol de jerarquía sin cargo, superiores no válidos, capacidades por rol. Ids internos, sin nombres | Gate §6, ejecutable por quien opere cada entorno |
| `docs/ARCHITECTURE.md` | Invariantes nuevas de la jerarquía de Route | Regla 3 de AGENTS.md |

**No se tocó:** Estado operativo, Zona horaria, WorkSession, Trip, GPS, Routing, millaje, odómetros, My Route, RTE08, Today/Activity/Reports (solo se leen en las pruebas), catálogo de capacidades ni roles por defecto. El *diff* no toca `location`, `offlineQueue`, `mileage`, `trips`, `worksessions` ni `app/core/rbac`.

---

## 3. Gate de datos (base local, solo lectura)

### 3.1 Inventario (`hierarchy_preflight`)

| Comprobación | Resultado |
|---|---|
| Compañías con más de un CEO vigente | **0**: la 0019 se aplicaría sin conflicto |
| Rol y cargo que no se corresponden | **5** en el tenant 1: ids 269, 271 y 272 (rol `supervisor`, cargo RM), 273 (`supervisor`, Sales) y 274 (`supervisor`, **COO con 3 directos**). Origen `CONFIRMED` por auditoría: cambios de rol por la pantalla general el 14-10 entre las 15:51 y las 15:54 |
| Rol de la jerarquía sin cargo | 0 |
| Cargos bajo un superior suspendido, retirado o sin cargo | 0 |

### 3.2 Regularización propuesta (no ejecutada)

- **Cómo se hace:** desde **CER Route → Users → Edit**, se devuelve a cada persona su rol: 274 → COO; 269, 271 y 272 → Regional Manager; 273 → Sales.
- **Por qué funciona sin tocar nada más:** su cargo y su superior ya son correctos. Con V1.4, esa edición **sincroniza rol y cargo en una transacción** y deja auditoría.
- **Lo que no hace falta:** ningún script de datos.

Tras regularizar, se puede aplicar la 0019.

### 3.3 CEO con 27 capacidades frente a 9 — **causa `CONFIRMED`; riesgo crítico**

- **De dónde salen:** de la **solicitud de cambio de permisos #8** del rol CEO.
  - La pidió el usuario 1 (owner) el 14-10 a las 15:45.
  - La **aprobó el usuario 267 (admin)** a las 15:47, con las **27 capacidades**.
  - Siguió el proceso legítimo de aprobación.
- **Qué concede:** al CEO, la **administración general**: `roles.*`, `rolepermissions.update`, `companies.update`, `integrations.manage`, `users.delete`, `route.records.adjust`, `route.vehicles.manage` y otras.
- **Por qué no es un efecto de la 0018:** la 0018 concede las 9 de su plantilla. Y no hay overrides por usuario: el modelo es solo por rol.
- **Clasificación:** **desviación de la plantilla aprobada (sobreprivilegio)**.
- **Lo que no hice:** quitar ni añadir capacidades. Corregirlo exige una nueva solicitud en Roles & Permissions **aprobada por CER**.
- **Además:** la solicitud **#9** (Regional Manager, 9 capacidades) está pendiente.

### 3.4 Riesgos de producción

- **No sé** si producción tiene CEO duplicados o incoherencias: **PENDING VALIDATION** con `hierarchy_preflight` en ese entorno.
- **Si los tuviera, la 0019 se detendría sin cambiar nada**, que es el comportamiento buscado.

---

## 4. Contratos, transacciones y auditoría

### 4.1 Vías que cambian rol o pertenencia, y su estado

| Vía | Antes | Ahora |
|---|---|---|
| `PUT /api/users/{id}` con cambio de rol de alguien con cargo | 200, sin sincronizar (H-1) | **409** `managed_in_cer_route`, sin cambios |
| `POST /api/users` / `PUT …` con un rol de la jerarquía o con `superior_user_id` | 200 si llevaba superior | **409** |
| `POST /api/users/{id}/reenrollment` con un rol de la jerarquía | 200: rol sin cargo | **409** |
| `POST /api/route/users/{id}/reenrollment` con un rol de la jerarquía | 200: rol sin cargo | Exige superior (422 sin él); cargo en la misma transacción |
| `PUT /api/roles/{id}` renombrando un rol de Route / `DELETE` | 200 | **409** |
| `/api/route/users` (alta y edición) | Rol, cargo y superior en una transacción | Igual, más CEO único |
| Suspender / retirar pertenencia | Sin cambios | Sin cambios (retirar con directos sigue dando 409) |

### 4.2 Retirar y Sustituir

| | Retirar (`POST /api/route/organization/{id}/retire`) | Sustituir (`…/replace`) |
|---|---|---|
| Cuerpo | `{version?, reason?, dry_run}` | `{successor_user_id, version?, reason?, dry_run}` |
| Para | Cualquier cargo; **CEO con equipo → 409** («use Replace manager») | CEO, COO, RM; otro cargo → 409 |
| Efecto | Directos → superior inmediato; indirectos intactos; quien sale, sin cargo y fuera de la compañía | Sucesor → cargo del saliente bajo su superior, rol del cargo; directos del saliente → sucesor; los directos propios del sucesor se quedan con él |
| Rechazos | 409: superior suspendido, relación no permitida, ciclo, versión obsoleta; 403: no `route_admin`; 404: otro tenant | Además: sucesor por encima (ancestro), a sí mismo, suspendido, `route_admin` o rol del núcleo → 409; de otro tenant → 404 |
| Garantías | Candado por compañía, recálculo con el candado tomado, un instante T, **todo o nada** (comprobado con un fallo inyectado) | Igual; cierra la fila del CEO saliente antes de abrir la del entrante (el índice único lo permite en la misma transacción) |
| Auditoría | Un `org_succession` (retire/replace) más un `org_assignment` por fila y un `user` delete (y un `user` update del rol del sucesor). Todos con `operation_id` y además el mismo `request_id` | |

### 4.3 Decisiones de implementación que conviene confirmar (DECISION REQUIRED)

- **D-a: quien sale deja la compañía** (baja existente). No se ofrece «suspender sin cargo», porque dejaría un rol de mando sin cargo (FR-01.5). Si CER quiere otra salida, por ejemplo pasar a otro rol, sería una ampliación.
- **D-b: los sucesores elegibles** son miembros activos con un rol de la jerarquía. No pueden serlo `route_admin` ni los roles del núcleo.
- **D-c: con el superior inmediato suspendido, retirar o sustituir se rechaza** («restore their access first»). No se elige un superior alternativo sin autorización.

---

## 5. Matriz de criterios de aceptación

| AC | Esperado | Implementado | Evidencia | Gap | Estado |
|---|---|---|---|---|---|
| AC-01 | El contrato general no desincroniza; 409 sin cambios parciales; lo no-Route sigue funcionando | Guarda en alta, edición, superior y readmisión, más nombres fijos de roles | `test_el_contrato_general_*` (owner, admin y route_admin; foto completa sin cambios), `test_readmitir_*`, `test_los_roles_de_route_*`; E2E `escritorio-access-control-409` | — | **COMPLETED** |
| AC-02 | Route: rol y superior atómicos; Edit precarga «Reports to», también tras recargar | Sin cambios en lo atómico (V1.3); arreglo del selector | `test_cambiar_rol_y_superior_es_atomico`; E2E precarga al abrir **y tras recargar** | — | **COMPLETED** |
| AC-03 | CEO suspendido no ofrecido; estados vacíos útiles | Filtro en `/options`; mensajes contextuales | `test_un_superior_suspendido_no_se_ofrece`, `test_superior_de_otro_tenant_o_inactivo`; E2E «No CEO assigned yet» | — | **COMPLETED** |
| AC-04 | Máximo un CEO, también en la base y en concurrencia; arranque sin CEO | Índice 0019 + servicio | `test_un_segundo_ceo_*` (API e `IntegrityError` en la base), `test_dos_altas_de_ceo_simultaneas_una_gana`, migración con duplicados detenida | La 0019 no se aplicó en tu base local (decisión del gate) | **COMPLETED** (local) |
| AC-05 | Retirar COO: directos al CEO, indirectos intactos, todo o nada | `succession.py` | `test_retirar_coo_*` (vista previa = ejecución, T único, auditoría), `test_un_fallo_a_mitad_*` | — | **COMPLETED** |
| AC-06 | Retirar RM: al COO/CEO inmediato; Sales nunca al COO | Ídem | `test_retirar_rm_*[rm_a, rm_b]` | — | **COMPLETED** |
| AC-07 | Sustituir CEO: todo, incluido Sales, al nuevo; un solo CEO | Ídem | `test_sustituir_ceo_*` (Today del nuevo CEO con Sales; COO sin Sales, 404 por id) | — | **COMPLETED** |
| AC-08 | Sustituir COO o RM atómico y auditado; rechazos | Ídem | `test_sustituir_coo_*`, `test_sustituir_rm_por_alguien_de_su_propio_equipo`, `test_sustituciones_invalidas_*` (5 casos), sucesor suspendido o de otro tenant, actores no autorizados (5), otro tenant 404, concurrencia, versión | — | **COMPLETED** |
| AC-09 | Suspender preserva y no delega; reactivar no duplica | Sin cambios (ya era así) | `test_suspender_y_reactivar_al_ceo_*` (filas idénticas) | — | **COMPLETED** |
| AC-10 | Alcances nuevos desde T; D-3; COO/RM sin Sales | Sin cambios de alcance; las operaciones abren periodos en T | `test_el_sucesor_no_hereda_jornadas_anteriores_a_t` (5,0 millas frente a 15,0 del CEO), más la batería V1.3 de alcance | Probado con la jornada antes y después de T; la jornada nocturna que cruza T está cubierta por el test V1.3 de traslado, no por uno nuevo de sustitución | **COMPLETED** |
| AC-11 | El preflight identifica discrepancias; no sanea sin autorización | Script de solo lectura y *preflight* de la 0019 | §3; `test_dos_ceo_vigentes_detienen_la_migracion_sin_cambios` | La regularización y la corrección de capacidades necesitan tu autorización | **COMPLETED** (gate), **DECISION REQUIRED** (datos) |
| AC-12 | Escritorio y móvil: Edit, mensajes, vista previa, confirmación; Roles & Permissions sin cambios fuera de lo autorizado | Diálogo y menú | E2E 4/4: `{escritorio,movil}-sustituir-vista-previa`, `-retirar-vista-previa`, `-tras-cambios` | Solo se cambió en Roles & Permissions la guarda de nombre | **COMPLETED** |
| AC-13 | Sin cambios en Estado, Zona horaria, My Route, RTE08, tracking, millaje u odómetros | *Diff* sin esos módulos | `git diff --stat` (§2); regresión de esas áreas en verde salvo los 5 E2E de §6 | — | **COMPLETED** |
| AC-14 | Suites honestas, migraciones verificadas, sin merge ni despliegue | §6 | §6 | Certificación del PO | **PENDING VALIDATION** |

---

## 6. Pruebas

| Lote | Tests | Resultado | Exit | Duración |
|---|---|---|---|---|
| 1. Contratos (`tests/test_*.py`) | 49 | 49 PASS | 0 | 19 s |
| Nuevos V1.4 (`test_hierarchy_integrity_v14`) | 41 | 41 PASS | 0 | — |
| Migraciones (0019 + roles) | 6 | 6 PASS | 0 | — |
| Jerarquía, migración de roles y readmisión (adaptados) | 110 | 110 PASS | 0 | — |
| 2. Integración completa, 1.ª vuelta | 1311 | **22 FAIL** | 1 | 848 s |
| 2b. Los 8 archivos afectados, adaptados | 316 | 316 PASS | 0 | 167 s |
| E2E relacionados (jerarquía V1.4/V1.3, usuarios, ciclo de vida, acceso, UX admin) | 36 | 35 PASS, **1 FAIL** → corregido, 8/8 | 1 → 0 | 441 s + 125 s |
| **Final: integración + contratos completos** | 1326 | **1310 PASS, 15 skipped, 1 FAIL (preexistente)** | 1 | 905 s |
| **Final: E2E completos** | 204 | **199 PASS, 5 FAIL (RTE06, ver abajo)** | 1 | 3136 s |
| Frontend `npm run check` (`tsc` + ESLint) | — | 0 errores | 0 | — |
| `uv run python -c "import app.main"` | — | OK | 0 | — |

### Fallos, uno por uno

- **22 en la 1.ª vuelta de integración (causa `CONFIRMED`): son efectos del cambio, no defectos.**
  - **21** eran tests que preparaban Supervisores por `/api/users` con superior. Es exactamente lo que DR-5 ahora rechaza.
    - **Qué se hizo:** se movieron a `/api/route/users`.
    - **Lo que no cambió:** los casos negativos de escalada siguen en `/api/users` y siguen dando 403.
    - **Resultado después:** 316/316.
  - **1** es el fallo preexistente de abajo.
- **1 E2E (`test_superadmin_crea_sales…`), causa `CONFIRMED`:** esperaba dos CEO como opciones; con el CEO único queda uno. Se actualizó la expectativa y pasó a 8/8.
- **Preexistente, causa `CONFIRMED`:** `test_provisioning_alignment::…twelve_and_two_capabilities` espera 12 capacidades para `route_admin` y el catálogo concede 16 desde RTE09 y V1.3.
  - **Por qué no es mío:** mi rama no toca el catálogo ni el aprovisionamiento (último cambio del catálogo: `e5371b6`).
  - **Por qué no lo corrijo:** el número certificado es decisión de CER.
- **5 E2E de RTE06** (ubicación sin conexión y umbral de recuperación de precisión): `test_a_location_captured_offline_is_not_lost` y 4 de `test_rte06_recovery_accuracy_browser`.
  - **Ejecutados aislados** (1027 s): fallan igual y de forma determinista. El servidor registra 0 ubicaciones aceptadas, o una coordenada distinta de la simulada.
  - **Preexistentes, `CONFIRMED`:**
    - mi *diff* no toca `location`, `offlineQueue` ni el frontend de ubicación;
    - son las «5 pruebas de ubicación sin conexión, sin diagnosticar» que ya figuraban como pendientes en el estado del proyecto antes de V1.4.
  - **Causa raíz: `UNVERIFIED`**, fuera de alcance. Sigue siendo una decisión pendiente de CER.

Las capturas están en `var/screenshots/hierarchy-v14/`, fuera del árbol versionado (convención del proyecto).

---

## 7. Migración, despliegue y rollback

**Despliegue, en este orden:**
1. **Antes de migrar,** ejecutar en cada entorno `uv run python -m app.db.scripts.hierarchy_preflight`.
   - Si hay **CEO duplicados**, CER elige al titular y se regulariza con «Replace manager» o la retirada **antes** de la 0019. Si no, la 0019 se detiene sin cambios.
   - Las **incoherencias rol/cargo** se regularizan desde CER Route → Users (§3.2). No bloquean la 0019, pero sí la certificación.
2. `uv run alembic -c app/alembic.ini upgrade head` (0019).
3. Desplegar el código y el bundle. Que todos **recarguen la aplicación**.
4. Revisar con CER las capacidades del rol CEO (§3.3).

**Rollback:**
- `alembic downgrade 0018_route_distinct_roles` quita el índice; no hay datos que deshacer.
- Revertir el código **reabre H-1**.
- Las operaciones ya ejecutadas son historial: append-only en auditoría, y periodos cerrados en `org_assignment`. Se corrigen con nuevas asignaciones, nunca editando filas.

**Sin cambios en** Estado operativo, Zona horaria, datos temporales, rutas ni millaje: ver §2 y AC-13.

---

## 8. Esfuerzo

| Tarea | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Backend: guarda, CEO único, sucesión, endpoints, migración y *preflight* | Hecho | ~900 LoC | media-alta | 5,0 |
| Frontend: formulario, diálogo, *thunks* | Hecho | ~400 LoC | media | 3,0 |
| Tests nuevos y adaptados (integración, migración, E2E) | Hecho | ~1000 LoC | media | 4,0 |
| Regresión, diagnóstico de fallos e informe | Hecho | — | — | 3,0 |
| **Total consumido** | | | | **≈ 15 h** |
| **Restante, sin certificar:** revisión del PO, regularización de datos, decisión sobre capacidades del CEO, despliegue | Pendiente (CER) | — | — | ~1–2 h de agente si CER pide ajustes, +10 % |
