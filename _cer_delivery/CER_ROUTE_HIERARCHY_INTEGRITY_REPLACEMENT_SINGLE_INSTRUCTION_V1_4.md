# CER Route — Jerarquía: integridad, reasignación ascendente y sustitución de responsables

**Instrucción única de desarrollo V1.4** · 14 de octubre de 2026  
**Destinatario:** programador CER Route y agente de desarrollo  
**Frente:** corrección y cierre de jerarquías/roles CER Route; continuación de V1.3, **sin crear otro módulo ni reconstruir el modelo**.  
**Autorización:** implementar únicamente el alcance y los controles de este documento; **no fusionar ni desplegar** sin certificación expresa de CER.

## 1. Context / Current State

**Fuente de evidencia primaria:** `CER_ROUTE_HIERARCHY_VACANCY_REPLACEMENT_AS_BUILT_DIAGNOSTIC_001.md` (14-10-2026). El diagnóstico se realizó sobre `dev` @ `20942dc`, migración `0018_route_distinct_roles`, e informó que V1.3/MR !90 estaba integrado. **Verificar SHA, migraciones y estado del entorno al iniciar:** no asumir que el entorno desplegado coincide con el diagnóstico.

AS-BUILT verificado por el agente:

- La jerarquía usa `org_assignment` (cargo, usuario, `superior_user_id`, períodos de vigencia), relación **persona → persona**; existen bloqueo por compañía, prevención de ciclos, auditoría y alcance histórico por `WorkSession.started_at`.
- **H-1 CRÍTICO:** `Access control → Users` / `/api/users` permite cambiar el rol de un jefe sin sincronizar o validar su cargo. La base local ya presentó **cinco casos** de rol `supervisor` con cargo de jefatura.
- **H-2:** CER Route → Users → Edit no siempre precarga el superior vigente.
- **H-3:** las opciones de `Reports to` pueden ofrecer un CEO suspendido, aunque el servidor lo rechaza al guardar.
- **H-4:** no existe unicidad del cargo CEO por compañía; se reprodujeron varios CEO vigentes.
- CER Route → Users **sí** muestra `Reports to` para cargos con superior, aun cuando no existan candidatos; Access control → Users usa el formulario compartido sin contrato Route y **no** muestra el campo. Son experiencias distintas; no deducir que el formulario Route oculta el campo por ausencia de CEO.
- El diagnóstico observó un rol **CEO con 27 capacidades** en base local frente al catálogo funcional esperado de **9**. **La causa no está probada.**
- No existe operación transaccional para sustituir un jefe ni para retirar definitivamente a un responsable transfiriendo sus subordinados al superior inmediato.

**Estado actual:** diagnóstico completado; funcionalidad V1.3 **no certificada** por CER hasta cerrar los hallazgos de integridad y validar la operación.

## 2. Objetivo y decisiones del Product Owner

Mantener una jerarquía **sencilla, visible, segura y continua ante cambios de personal**, sin modelar plazas vacantes independientes de los usuarios ni añadir complejidad organizacional.

### Decisiones confirmadas

1. **Arquitectura A:** conservar `org_assignment`, su relación persona → persona y la política de alcance vigente. **No** introducir `org_position`, `org_occupancy`, plazas, organigramas nuevos ni tablas de ocupación.
2. **Un único CEO titular vigente por compañía (tenant)**; cantidad **sin límite artificial** de COO, Regional Manager, OSM, Supervisor y Sales debajo, respetando relaciones válidas. Los niveles intermedios pueden omitirse.
3. **Sales reporta directamente al CEO**, nunca al COO/RM; conserva My Route y Activity propia, sin funciones administrativas.
4. Si un **COO o Regional Manager sale definitivamente y no hay reemplazo**, sus subordinados **directos pasan al superior inmediato** de quien sale. Los descendientes indirectos mantienen sus relaciones; no hay que editar toda la rama.
5. Si se **sustituye** a un responsable, el equipo pasa al nuevo responsable **en una sola transacción**, preservando las restricciones jerárquicas y la historia.
6. Si sale un **CEO con subordinados**, no se trasladan sus subordinados al COO: **es obligatorio designar un CEO sustituto** en la misma operación. Nunca crear un segundo CEO titular vigente ni dejar Sales bajo un superior no permitido.
7. Una **ausencia temporal/suspensión** conserva las relaciones y **no delega automáticamente permisos**. Una salida definitiva es una operación diferente.
8. Conservar D-3: la visibilidad histórica responde a períodos de supervisión y a `WorkSession.started_at`; el entrante no adquiere por defecto jornadas previas.
9. **Estado operativo, Zona Horaria y toda la lógica temporal quedan estrictamente sin cambios.**

### Decisiones de seguridad operativa para esta ejecución

- **DR-5:** un cambio de rol Route que afecte a personas de la jerarquía ejecutado desde el contrato general `/api/users` debe **rechazarse en servidor con 409** y mensaje accionable: `Use CER Route → Users`. No sincronizar ni inferir superiores desde la pantalla general.
- **Reemplazo y retiro jerárquico de jefes con subordinados:** inicialmente **solo `route_admin` debidamente autorizado dentro del tenant**; no usar `owner`/`admin` del Core como equivalentes implícitos. Esta restricción es de mínimo privilegio; **no delegar más funciones de sustitución** a CEO/COO/RM sin aprobación posterior.
- Para asignación inicial y edición ordinaria conservar la delegación aprobada, las restricciones por tenant y la prohibición de escalamiento.

## 3. Scope / Out of Scope

### Dentro

- H-1: cerrar todas las vías reales que permiten dejar `role_id` y `org_assignment.position` incompatibles (ambos montajes de usuarios, variantes de actualización/acceso pertinentes y cualquier endpoint equivalente). Mantener un **único camino autorizado** para modificaciones jerárquicas desde CER Route → Users.
- H-2 y H-3: persistencia/precarga de `Reports to`, candidatos realmente elegibles, estados vacíos y mensajes útiles.
- H-4: un CEO titular vigente por compañía, con protección a concurrencia y tratamiento seguro de datos anteriores.
- Dos operaciones funcionales distintas sobre jefes: **Retirar responsable** (reasignación ascendente) y **Sustituir responsable** (traslado al sucesor). Reutilizar servicio, validaciones, auditoría y APIs de Route existentes.
- Diagnóstico y plan de saneamiento **controlado** de inconsistencias existentes; pruebas de regresión, seguridad, UI y migración cuando corresponda.

### Fuera

- Puestos vacantes independientes de usuarios, múltiples CEOs titulares en un mismo tenant, cadenas laterales OSM↔Supervisor, atribución de Sales a COO/RM, cargos nuevos.
- Rediseño del módulo Users, pantallas nuevas de organigrama, dashboards por rol, modificación de los flujos My Route/Activity/Today/Reports/millaje y de la navegación, salvo el control mínimo de jerarquía en Users.
- Core RBAC general, salvo **guarda puntual e indispensable** que evite el bypass H-1 sin contaminarlo con cálculos de negocio de Route.
- Modificaciones a Estado, Zona Horaria, UTC/DST, offsets, `session_date`, WorkSession, Trip, odómetros, GPS, routing o costeo.
- Correcciones generales S-2/S-3 fuera de este frente; documentarlas y escalar si impiden certificar seguridad.
- Migraciones o reparaciones automáticas de datos productivos sin inventario, autorización y respaldo verificable.

## 4. Functional Requirements / Business Rules

### FR-01 — Coherencia única de rol y cargo; cierre de H-1

1. Definir y aplicar **la misma validación server-side** en todos los puntos que puedan alterar una pertenencia/rol Route. Localizar consumidores efectivos de `/api/users`, `/api/route/users`, acceso/suspensión, actualización individual y cambios de rol indirectos.
2. Si una petición del contexto **Access control general** intenta cambiar el rol de un usuario que **está** en la jerarquía Route, o crear/sustituir una asignación jerárquica por una vía sin `Reports to`, responder **409** con mensaje accionable; **sin actualizar parcialmente ni `UserCompany` ni `org_assignment`**. No bloquear la edición no jerárquica legítima del núcleo.
3. Desde **CER Route → Users** la modificación legítima debe actualizar en **una transacción** rol, cargo, superior y período conforme al contrato aprobado. No permitir que alguno quede desincronizado ante fallo o carrera.
4. Conservar rutas y comportamientos de roles `route_admin`, `owner`, `admin`, `manager` y usuarios del Core que **no** afecten la jerarquía Route. No dar a estos roles privilegios Route adicionales por ser roles generales.
5. Rechazar cualquier ruta restante capaz de crear un `role=supervisor` con `position=coo`, un rol de mando sin cargo o cualquier combinación inconsistente sin una transición explícita válida. Verificar también edición y retiro de pertenencias; no corregir datos ocultando filas en UI.

### FR-02 — CEO único, compañía operativa y bootstrap

1. Permitir **cero CEO** solo durante aprovisionamiento inicial (o después de haber quedado la compañía sin estructura operativa); se podrá crear el primero por Superadmin Route. Para altas de cargos subordinados, debe existir un CEO elegible.
2. Impedir **dos asignaciones CEO titulares vigentes** en el mismo tenant: protección tanto en servicio (bloqueo/concurrencia) como mediante **invariante de base**, de preferencia índice único parcial sobre `company_id` para `position='ceo' AND valid_to IS NULL` o una garantía equivalente demostrable. Los CEO históricos cerrados no cuentan; un CEO suspendido **con cargo vigente sigue ocupando el único puesto** y no autoriza crear otro por una vía lateral.
3. Para sustituir CEO-A por CEO-B, cerrar la asignación de A y activar B **en la misma transacción** y con orden compatible con la unicidad; no permitir una ventana visible con dos CEOs o un organigrama sin autoridad por una ejecución parcial.
4. **Preflight de datos antes de migrar:** contar CEOs vigentes por tenant, roles/cargos discordantes y relaciones inválidas. Si hay duplicados o discrepancias, **bloquear la aplicación de restricciones incompatibles** y entregar un inventario mínimo anonimizado y un plan de regularización aprobado. No elegir al CEO «correcto» ni borrar/modificar usuarios por inferencia.
5. Si se requiere migración para la invariante, diseñar upgrade seguro, datos existentes, índices y rollback; sin reescribir historial.

### FR-03 — «Retirar responsable» sin sustituto (reasignación ascendente)

1. Operación destinada a la **salida definitiva** de un COO o RM con subordinados; **no** equivale a suspender temporalmente al usuario.
2. Dentro de una **misma transacción**, validar actor, tenant, superior saliente vigente/elegible, directos afectados, roles y estructura resultante. Obtener un instante común de transición y bajo candado/versión existente:
   - pasar **únicamente los subordinados directos** al superior inmediato del jefe que sale;
   - preservar las relaciones de los descendientes indirectos y todos los datos operativos;
   - cerrar los períodos anteriores, abrir los nuevos y retirar/cerrar el cargo y acceso organizacional del saliente mediante los **estados de baja ya existentes** (no inventar estados), dejando claros permisos y pertenencia resultantes.
3. Verificar `PADRES_PERMITIDOS` para **cada** nueva relación y reglas de niveles opcionales. Ejemplos válidos: RM bajo COO/CEO; OSM y Supervisor bajo COO/CEO. **Nunca trasladar Sales al COO**. Si algún destino no es válido, responder con error explícito y **rollback completo**; no seleccionar un superior alternativo sin autorización.
4. Una salida de CEO con estructura debe **bloquearse** salvo que se use «Sustituir responsable» con nuevo CEO en la misma operación. Si la compañía está vacía, aplicar las reglas seguras de cierre sin generar un segundo CEO.
5. Para una persona con **cero subordinados**, preservar el flujo actual de baja ordinaria sin cambios innecesarios. La nueva operación debe evitar la necesidad de editar cada subordinado manualmente.
6. El estado posterior del usuario saliente debe ser consistente con su acción explícita (baja/suspensión, según el caso), sin asignarle de manera arbitraria el rol Supervisor, Sales u otro cargo.

### FR-04 — «Sustituir responsable» (sucesor identificado)

1. Disponible para CEO, COO o RM. Actor autorizado selecciona el **saliente** y la **persona entrante** del mismo tenant. Identificar el nuevo cargo y superior conforme a reglas existentes; no inventar un ocupante.
2. En una **operación transaccional única**, promover/asignar al entrante al cargo del saliente, ubicarlo en su superior autorizado, trasladar todos los subordinados directos del saliente y cerrar/retirar el cargo del saliente según la acción confirmada; mantener las ramas preexistentes legítimas del entrante sin duplicar relaciones o producir ciclos.
3. Permitir que el entrante ya sea miembro de la misma organización; validar especialmente promociones desde la rama del saliente y casos de un entrante con su propia rama. Si el resultado no puede preservarse **sin ciclos, duplicidades ni relaciones prohibidas**, devolver error claro y no hacer nada. No forzar una migración de puesto para lograrlo.
4. Sustitución CEO: respetar **un CEO por compañía**, mover **Sales al nuevo CEO**, no al COO; CEO saliente pierde autoridad desde T. Sustitución COO/RM: mantener las reglas vigentes de rama y exclusión de Sales.
5. Auditoría agrupada por un **identificador de operación** (`replacement_id` o correlativo equivalente), con actor, tenant, motivo, timestamp, saliente/entrante, rol/cargo previo y posterior y las relaciones transferidas. No registrar datos sensibles innecesarios.
6. Usar los mecanismos de transacciones/bloqueo/versiones vigentes; si cualquier validación o actualización falla, **ningún cambio** debe persistirse.

### FR-05 — Ausencia temporal y datos históricos

1. **Suspender no es retirar:** la suspensión mantiene `org_assignment` y sus descendientes; solo revoca las capacidades/sesión del usuario según el contrato existente. No crea un CEO nuevo ni promueve al COO automáticamente.
2. En operaciones históricas, preservar D-3: antes/después de T las ventanas de relación son contiguas, sin solapes; un supervisor o jefe movido mantiene sus WorkSessions y viajes; las consultas de Activity, Reports y Excel usan `WorkSession.started_at` según período autorizado. No conceder al sustituto historial anterior a T por efecto de haber recibido el equipo.
3. Asegurar efecto inmediato para Today/Users: el saliente no conserva acceso administrativo a la rama; el entrante solo obtiene el alcance vigente y permitido; ningún usuario puede consultar otra compañía o Sales desde COO/RM por API directa.
4. Para cambios con superior suspendido/inactivo, **no ofrecerlo como candidato** y mantener un mensaje claro. No confundir una suspensión con una vacante estructural.

### FR-06 — Formularios de usuarios (corrección mínima)

1. En **CER Route → Users → Edit**, `Reports to` siempre es visible para roles que requieren superior. Debe **precargar** de forma fiable el superior vigente al abrir, al llegar las opciones asíncronas, tras guardar y al reabrir; nunca sobrescribir cambios del usuario por carreras de datos.
2. Los candidatos deben filtrarse en servidor por compañía, pertenencia activa, cargo correcto, relaciones permitidas, ciclo y scope delegado. **CEO suspendido no se ofrece** si el servicio no permite asignaciones bajo él.
3. Sin superiores elegibles, mantener el campo visible (no desaparecer ni fallar silenciosamente) con mensaje contextual: «No CEO assigned yet — assign a CEO first» u otro específico según cargo. No guardar una relación inválida ni inventar un parent.
4. En **Access control → Users**, mantener el contrato general. Para un usuario de jerarquía Route, impedir cambios de rol jerárquicos con información clara («Managed in CER Route → Users») o estado de solo lectura. El **servidor igualmente debe responder 409** ante intento directo.
5. Agregar acciones mínimas «Retirar responsable» / «Sustituir responsable» donde sea coherente con Users de Route; confirmar antes de ejecutar y presentar resumen de personas afectadas y destino, sin rediseñar el formulario ni crear una página nueva. UI escritorio y móvil.
6. No modificar otros campos del formulario (Estado, Zona Horaria incluidos).

## 5. Roles, límites jerárquicos y permisos

**Roles existentes a conservar**, sin duplicar ni recrear catálogos: `CEO`, `COO`, `Regional Manager`, `OSM`, `supervisor`, `Sales`, `route_admin`; `route_manager` es legado y debe seguir sin permisos tenant-wide.

| Cargo del usuario | Superior permitido | Alcance administrativo |
|---|---|---|
| CEO | Sin superior; **solo uno vigente por tenant** | Su árbol, incluye Sales directo |
| COO | CEO | Su rama, sin Sales |
| Regional Manager | COO o CEO | Su rama, sin Sales |
| OSM / Supervisor | RM, COO o CEO | Actividad propia |
| Sales | **Solo CEO directo** | Actividad propia |
| `route_admin` | Fuera de árbol de mando | Alcance de administración autorizado del producto, sin modificaciones |

- Ningún rol operativo puede autoconcederse alcance. La operación de continuidad no es una vía para cambiar roles en Core.
- Los `route_admin` no pueden intervenir fuera del tenant autorizado; no equiparar un administrador genérico con Route Superadmin.
- Listados de usuarios, Today, Activity administrativa, Reports, Excel, `organization/options` y endpoints por ID deben continuar aplicando scopes de Route en servidor; mantener 403/404 seguros y filtros anteriores a la agregación.

## 6. Gate previo — calidad de datos y capacidades

**Antes de ejecutar reparaciones o instalar una restricción de CEO único en una base existente**, entregar evidencias mínimas de:

1. **Inconsistencias rol/cargo:** quiénes y cuántos (IDs internos en reporte restringido o datos anonimizados), estado de pertenencia, cargo, rol, superior, rama afectada y origen conocido. El diagnóstico local identifica cinco casos, pero no asumir que producción sea idéntica.
2. **CEO múltiples por tenant:** listar cantidad/estado y efectos sobre descendientes; proponer regularización explícita, reversible y auditada. **No escoger al CEO titular automáticamente**.
3. **CEO 27 vs 9 capacidades:** contrastar definición del catálogo, roles efectivos, overrides, asignaciones por tenant, provisioning y posibles permisos extras. Clasificar qué es legítimo o desvío; **no quitar ni añadir capacidades silenciosamente**. Si se detecta riesgo de sobreprivilegio, elevar hallazgo crítico y bloquear certificación hasta corregir con aprobación.
4. Confirmar transacciones y rollback con copia de prueba, no en producción. Cualquier script de corrección de datos debe ser **separado, explícitamente autorizado, idempotente, con dry-run y auditoría**; no se ejecuta por tener autorización de implementar código.

**Regla de continuidad del desarrollo:** se puede implementar y probar en un entorno aislado limpio. **Bloquear migración/despliegue en un tenant con datos inconsistentes hasta su regularización aprobada**. No maquillar con datos de prueba la situación de los entornos existentes.

## 7. API / Servicios / Auditoría / Migración

- Reutilizar el módulo Route `organization`, la política de scope, servicio de concurrencia y transacciones. Elegir contratos HTTP Route para `retire` y `replace` consistentes con el repositorio y documentar request/response, validaciones, errores 403/404/409/422, versión y motivo. No imponer nombres de rutas si los contratos existentes aconsejan otra forma.
- Para `Access control` crear **guarda transversal mínima** que detecte miembros con asignación Route y rechace cambios de roles incompatibles; mantener lógica del árbol y de transferencia **dentro de Route**, no en Core.
- Las operaciones deben bloquear conflictos por versiones y por pertenencia y aplicar el mismo instante de transición a todas las asignaciones de la operación.
- Auditar evento principal y cambios afectados de forma correlacionable, sin filtrar PII por respuestas fuera de scope; preservar eventos previos.
- Una restricción DB de CEO único puede requerir **migración aditiva**; no aceptar la promesa genérica «sin migraciones» si no garantiza la unicidad en concurrencia. Preflight y plan de rollback obligatorios.
- La instrucción no autoriza una migración de puestos ni modificación del esquema de jornada/routing/timezone.

## 8. Acceptance Criteria — Expected → Evidence

| ID | Criterio observable |
|---|---|
| AC-01 | Cambiar rol de COO/RM/CEO desde `/api/users` o cualquier ruta general no permite desincronizar cargo; responde 409 sin cambios parciales y conserva acceso legítimo no Route. |
| AC-02 | En Users Route, cambiar rol y superior mantiene consistencia atómica; Edit precarga `Reports to` aun tras recarga y consulta asíncrona. |
| AC-03 | CEO suspendido/no elegible no aparece como parent y la UI muestra estados vacíos útiles, sin ocultar `Reports to`. |
| AC-04 | **Máximo un CEO vigente por tenant**, protegido también en la base y en concurrencia; múltiples CEOs históricos permitidos. Bootstrap sin CEO no permite colgar subordinados inválidamente. |
| AC-05 | Retirar COO con CEO por encima transfiere sus **directos** al CEO; hijos de RM mantienen su RM; saliente pierde su cargo/autoridad; cero cambios parciales. |
| AC-06 | Retirar RM transfiere OSM/Supervisor a su COO/CEO inmediato; Sales no se asigna a COO bajo ninguna circunstancia. |
| AC-07 | Sustituir CEO-A por CEO-B transfiere COO/RM/OSM/Supervisor directos y Sales al nuevo CEO, con **un único CEO** y sin fuga de alcance histórico. |
| AC-08 | Sustituir COO o RM transfiere su equipo con operación atómica y auditoría correlacionada; rechaza actor/entrante/parent ilegítimos, ciclos y cross-tenant. |
| AC-09 | Suspender temporalmente al CEO/COO/RM preserva jerarquía, no activa reemplazo ni otorga permisos; reactivar no duplica asignaciones. |
| AC-10 | Today, Activity, Reports, Excel y Users reflejan los alcances nuevos desde T y sus historiales por D-3; COO/RM nunca ven Sales, ni por ID directo. |
| AC-11 | Preflight identifica discrepancias locales (rol/cargo, CEO múltiple, 27 capacidades); no sanea ni aplica restricción riesgosa sin autorización separada y respaldos. |
| AC-12 | Escritorio/móvil: Edit, mensajes, vista previa de salidas/sustituciones y confirmación; Roles & Permissions no cambia fuera de la autorización. |
| AC-13 | Sin cambios de Estado, Zona Horaria, My Route, RTE08, tracking, millaje, odómetros ni datos históricos; regresión protegida. |
| AC-14 | Suite focalizada y general con resultados honestos, migraciones verificadas, documentación de errores previos/nuevos y evidencias reproducibles; **sin merge/deploy sin certificación de CER**. |

## 9. Tests Required

**Integración / seguridad**

- Matriz actor: `route_admin`, CEO, COO, RM, Supervisor, OSM, Sales y rol general del núcleo; un tenant y otro. Probar intentos mediante `/api/users`, `/api/route/users`, `/api/route/organization` y rutas equivalentes usadas por UI; verificar 409/403/404, incluyendo acceso por ID conocido.
- Incoherencia rol↔cargo; edición inocua de datos generales; ruta autorizada desde CER Route; usuarios legados sin asignación; suspensión y readmisión.
- Concurrencia con dos CEOs propuestos, dos sustituciones simultáneas, retiradas simultáneas, cambio de rol paralelo y rollback por fallo inyectado tras mover parcialmente subordinados.
- Retiro COO→CEO, RM→COO y RM→CEO, último CEO con hijos (bloqueado), reemplazo CEO incluyendo Sales, COO y RM, reemplazo con sucesor ya perteneciente a la rama, resultado inválido/ciclo, superior suspendido y tenant diferente.
- D-3 por tiempos reales (incluida jornada nocturna que cruza T); Today actual, Activity/Reports/Excel históricos y exportaciones; no modificar millaje oficial ni timestamps.
- Role catalog efectivo CEO/COO/RM (9 previstas frente a 27 observado), `route_admin` sin ampliación, OSM/Supervisor/Sales equivalentes y sin administración. Reportar desviaciones, no ajustar capacidades hasta establecer causa/autorización.
- Migración de índice CEO único con base limpia y datos duplicados: detención explícita, upgrade/downgrade seguro, índice funcional, sin reasignación implícita de tenants.

**E2E / UX / regresión**

- Browser de escritorio y móvil: Route → Users y Access Control → Users con sus diferentes contratos; crear/editar/reabrir y recargar; precarga de superior y opciones filtradas; mensajes de no CEO y CEO suspendido; acciones de retiro/sustitución con confirmación y feedback.
- Escenario visible: CEO-A → COO-A → RM-A → Supervisor y CEO-A → Sales. Retiro COO-A, reemplazo RM-A, reemplazo CEO-A→CEO-B; comprobar visualización según usuario y ausencia de Sales para COO.
- Regresiones enfocadas a Users, roles, Today, Activity personal/administrativa, Reports, Excel, y conservación de Estado/Zona Horaria. Revisar el diff y corroborar no interferencia.

## 10. Checkpoints internos (no nuevos proyectos ni MRs obligatorios)

**CP-1 — Seguridad e integridad:** verificar entornos; documentar preflight; cerrar H-1, H-2, H-3 y establecer la garantía CEO único en ambiente seguro. Entregar pruebas reproducibles antes de avanzar a operaciones jerárquicas.

**CP-2 — Continuidad:** implementar retiro ascendente y sustitución de CEO/COO/RM como operaciones atómicas, con mensajes claros, auditoría y pruebas negativas de alcance/Historia.

**CP-3 — Certificación candidata:** regresión, E2E desktop/móvil, inventario de diferencias por entorno, instrucciones de despliegue/rollback y reporte final.

Estos checkpoints organizan **una sola instrucción** y un frente de corrección; no implican nuevas autorizaciones arquitectónicas ni modificaciones automáticas de producción.

## 11. Deliverables

Entregar **un único reporte final Markdown** bajo un nombre consistente, por ejemplo: `CER_ROUTE_HIERARCHY_INTEGRITY_REPLACEMENT_IMPLEMENTATION_REPORT_001.md`, que incluya:

1. Base SHA, rama/MR, migraciones, estado real merge/deploy y diferencias con el diagnóstico.
2. Matriz **Expected → Implemented → Evidence → Gap → Impact** por AC-01 a AC-14; clasificar `COMPLETED`, `PARTIAL`, `BLOCKED`, `PENDING VALIDATION`, `DEVIATION` y `DECISION REQUIRED`, sin llamar «completo» a lo no evidenciado.
3. Resultado del **gate de datos**: inconsistencias y CEO duplicados por tenant, causa de «27 vs 9 capacidades», riesgos de producción y propuesta de regularización **sin ejecutarla**.
4. Contratos API, transacciones, garantías de unicidad, política de reemplazo/retiro, motivos/errores y auditoría con correlación.
5. Pruebas unitarias, integración, autorización directa, E2E y regresión general, incluyendo fallos previos, nuevos, no ejecutados y limitaciones del entorno. Evitar suites que comparten base de tests concurrente.
6. Evidencias de UI, escritorio y móvil, incluyendo vista previa antes de confirmar y el árbol preservado después de cambios.
7. Pasos de migración, provisioning y rollback, y evidencia de **cero cambios a Estado, Zona Horaria, datos temporales, rutas y millaje**.

**Definition of Done:** la jerarquía no puede romperse mediante ninguna ruta de usuarios; solo existe un CEO titular vigente por compañía; la salida de un COO/RM conserva su estructura bajo el superior inmediatamente anterior; la sustitución de un CEO/COO/RM mueve toda su rama válida en una transacción; Sales sigue bajo CEO; el historial y la seguridad por tenant siguen correctos; las dos pantallas explican claramente su propósito. **Sin evidencia o sin validación del Product Owner, la función permanece pendiente de certificación.**
