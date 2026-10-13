# CER Route — Jerarquía organizacional, RBAC y Data Scope

**INSTRUCCIÓN ÚNICA Y CONSOLIDADA — Control B (Implementación) + Control C (Pruebas y Entrega) | V1.1**  
**Fecha:** 2026-10-13  
**Dirigido a:** Programador y agente técnico de CER Route  
**Estado:** **AUTORIZADO PARA IMPLEMENTAR CON LOS LÍMITES EXPRESOS DE ESTE DOCUMENTO**  
**Frente:** Jerarquía organizacional + RBAC + Data Scope (**un solo checkpoint funcional**)  
**Referencia diagnóstica, NO requisito de lectura para ejecutar:** Control A, `CER_ROUTE_ROLE_HIERARCHY_RBAC_DATA_SCOPE_IMPLEMENTATION_REPORT.md`, MR !88, basado en `dev` `153f9e6`.

> **FUENTE ÚNICA DE INSTRUCCIONES.** Este archivo incorpora el alcance y las decisiones D-1, D-1b, D-1c, D-2, D-3 y D-4 del Product Owner. Sustituye las instrucciones V1.0 anteriores y la autorización separada como **texto ejecutable**. No sumar tareas ni condiciones de documentos precedentes como si fueran instrucciones independientes. Consultar Control A únicamente para verificar evidencias y rutas reales del repositorio. Entregar **un único informe MD final** al terminar; no generar checkpoints nuevos.

## 1. Context y situación actual

El Control A confirmó que CER Route tiene hoy dos roles de producto (`supervisor` y `route_admin`), no tiene relación jerárquica persistida y varias consultas de Today, Activity y Reports están limitadas por tenant, pero no por rama organizacional. `UserCompany` conserva una pertenencia y un rol por usuario y compañía; `SupervisorProfile` no define cargo o superior.

El informe del agente **no acredita desarrollo**: no se ha implementado código de jerarquía. Las decisiones del PO, incorporadas íntegramente en este archivo, resuelven la puerta de decisión y permiten implementar en este mismo frente, **sin crear nuevos checkpoints ni repetir el preflight**. Antes de modificar archivos, validar que las rutas, el catálogo y los servicios identificados en Control A sigan vigentes en `dev` desde `153f9e6`; si cambiaron, adaptar los puntos de integración sin ampliar el alcance ni abrir otro preflight.

### Evidencia AS-BUILT que debe respetarse

Según el Control A del 13/10/2026 (verificar contra `dev` antes de implementar):

- `UserCompany` tiene un rol de pertenencia por compañía y actualmente **no existe** estructura persistente de cargo/superior.
- Los roles Route de producto son `supervisor` y `route_admin`; `supervisor` tenía dos capacidades y `route_admin` **16** en el inventario. Esto no autoriza cambiar `route_admin`.
- Today, Activity administrativo y Reports/Excel consultaban toda la compañía; `/api/activity-explorer/me` ya exponía el contexto personal de RTE08.
- Permisos se recomputan por petición; auditoría `audit_event` y concurrencia transaccional existen para reutilización.
- El fallo previo de `test_provisioning_alignment` comparaba **16** capacidades reales contra **12** esperadas. Preservar el catálogo y reportar el resultado sin maquillar la prueba.

**Clasificación:** estos son hechos reportados por el agente en su preflight, no una certificación independiente del estado actual del repositorio. Si el código cambió después, documentar el AS-BUILT real y aplicar la decisión aprobada sin ampliar alcance.

## 2. Objective

Entregar una jerarquía real y auditable por compañía, con permisos funcionales y acceso a datos por rama, que permita a CEO, COO y Regional Manager consultar y gestionar exclusivamente a sus subordinados autorizados, sin reducir la seguridad de otras APIs ni introducir pantallas nuevas.

**Invariante de producto:** **OSM = Supervisor** en permisos, menús y acceso a datos propios. Sus cargos son distintos solo para organización; están en el mismo nivel y **no existe relación de superioridad entre ellos**.

## 3. Decisiones confirmadas — no volver a consultar

| Decisión | Resultado obligatorio |
|---|---|
| D-1 | Crear rol de producto `route_manager` para CEO, COO y RM; el cargo, no otro rol, diferencia el nivel. Capacidades base ya existentes y autorizadas: `route.worksession.execute`, `route.standardvalues.read`, `route.live.read`, `route.activity.read`, `route.reports.read` y `route.reports.export`. Las capacidades `users.read/create/update` quedan sujetas a la guarda de seguridad indicada abajo. Conservar `route_admin` sin cambios no aprobados. |
| D-1b | `route.reports.export` se permite a `route_manager` solo con el mismo alcance autorizado de Reports. |
| D-1c | No conceder `users.delete` a `route_manager`. |
| D-2 | Administración delegada: `route_admin` gestiona Route en su tenant conforme a privilegios vigentes; CEO administra solo descendientes COO/RM/OSM/Supervisor; COO solo descendientes RM/OSM/Supervisor; RM solo OSM/Supervisor de su rama. OSM y Supervisor no administran. Prohibido actuar sobre sí mismo, pares, superiores, ramas ajenas o tenants ajenos, ni escalar a `route_admin`/plataforma. |
| D-3 | Historial **por período de relación**, no por jerarquía vigente. Atribuir toda una WorkSession al árbol vigente en el instante absoluto `WorkSession.started_at`, no por `session_date`; vigencias `[valid_from, valid_to)`. |
| D-4 | Sin asignaciones inferidas ni backfill de cargos/superiores en usuarios existentes. Asignación inicial exclusivamente expresa por administrador autorizado. Si falta jerarquía, conservar self-scope y no conceder acceso administrativo a otros usuarios. |

**Condición de seguridad sobre D-1:** `route_manager` queda aprobado como rol funcional y debe poder consultar Today, Activity y Reports únicamente en su ámbito; **pero `users.read`, `users.create` y `users.update` no se conceden automáticamente** hasta acreditar que su uso mediante *todas* las APIs queda restringido a Route y a la rama autorizada. Si no es posible con el contrato actual, implementar los componentes seguros y bloquear **solo** la delegación riesgosa, presentando una alternativa concreta para aprobación. **No inventar permisos nuevos unilateralmente**.

## 4. Roles, jerarquía y delegación

Niveles organizacionales: `CEO (4) > COO (3) > Regional Manager (2) > OSM (1) = Supervisor (1)`; **Superadmin CER Route** es una facultad administrativa dentro del tenant, no un eslabón obligatorio de la cadena.

| Actor | Visibilidad administrativa, si posee la capacidad | Cargos inferiores que puede asignar | Rol de producto que puede asignar |
|---|---|---|---|
| `route_admin` autorizado | Tenant autorizado de CER Route | CEO, COO, RM, OSM, Supervisor | Según política preexistente del administrador Route; sin ampliar privilegios de plataforma |
| CEO / `route_manager` | Descendientes de su rama | COO, RM, OSM, Supervisor | `route_manager` a COO/RM; `supervisor` a OSM/Supervisor |
| COO / `route_manager` | Descendientes de su rama | RM, OSM, Supervisor | `route_manager` a RM; `supervisor` a OSM/Supervisor |
| RM / `route_manager` | Descendientes de su rama | OSM, Supervisor | `supervisor` |
| OSM / `supervisor` | Actividad propia | Ninguno | Ninguno |
| Supervisor / `supervisor` | Actividad propia | Ninguno | Ninguno |

Permitir niveles intermedios opcionales (p. ej., CEO → RM → Supervisor y COO → Supervisor). Un usuario puede tener **a lo sumo un cargo y superior vigentes** por compañía. El superior debe ser estrictamente más alto; prohibir ciclos, relaciones laterales, autoasignación y cruces de tenant. La asignación y la modificación se hacen con permisos + alcance en servidor, no mediante validación exclusiva del formulario.

**Caso de creación delegada:** un manager solo puede crear un usuario de Route en su ámbito y asignarlo a sí mismo o a un superior subordinado válido dentro de su rama; jamás puede dejar una nueva persona fuera de su ámbito para ampliar su propia autoridad.

## 5. Control B — Implementación requerida

### B1 — Modelo persistente y auditoría

1. Reutilizar las entidades de tenant y pertenencia de usuario. Implementar una estructura **aditiva** de asignaciones históricas (la propuesta `org_assignment` es válida), con `company_id`, `user_id`, `position`, `superior_user_id`, `valid_from`, `valid_to`, autor y protección de concurrencia.
2. Vigencias como instantes absolutos, con intervalos **`[valid_from, valid_to)`** y una sola asignación abierta por usuario/tenant. Sin rellenar relaciones anteriores inventadas ni cambiar WorkSessions históricas.
3. Validar integridad de tenant en FK/servicios, jerarquía estricta, unicidad, ausencia de ciclos y transacciones concurrentes. Probar la migración en ambiente aislado, incluida reversión compatible.
4. Cada cambio de cargo o superior debe cerrar la asignación vigente y crear la nueva con vigencias no solapadas; auditar actor, tenant, instante, entidad, valores previos/nuevos y motivo cuando aplique. Evitar inconsistencias al reasignar gestores con descendientes; rechazar o resolver de forma transaccional sin romper invariantes.
5. Mantener el Core transversal libre de lógica específica de organización de Route. Ubicar la política en el dominio apropiado y ofrecer contratos reutilizables, sin imponer la ruta de archivo sugerida por Control A si contradice la modularidad vigente.

### B2 — Política única de autorización y alcance

1. Reutilizar autenticación y permisos actuales. Para cada lectura o escritura evaluar **tenant + permiso funcional + data scope + nivel/capacidad delegable**.
2. Evaluar alcance del actor en cada petición o con estrategia segura que invalide inmediatamente las revocaciones. Para Today utilizar la rama **actual**; para historia, reconstruir la cadena jerárquica **válida al inicio de cada WorkSession**.
3. Aplicar filtros **server-side antes de agregar, contar, paginar, ordenar y exportar**; una lista vacía no implica acceso total. Si no hay cargo/ramas configuradas, un `route_manager` no ve subordinados ni historia ajena.
4. Usuarios suspendidos/desactivados: respetar exclusión de operaciones vivas sin eliminar historia consultable legítimamente según permisos y período.
5. Un ID fuera de alcance no debe revelar existencia (p. ej., 404 donde ese sea el contrato). Verificar también búsquedas, selectores, detalles, exportación e identificadores suministrados directamente.
6. **No introducir equivalencias nuevas** entre roles de plataforma (`owner`, `admin`, `manager`) y `route_admin`; verificar el contrato actual y conservar solo las equivalencias aprobadas.

### B3 — Guardar todas las vías de administración delegada (bloqueo de seguridad)

1. Inventariar rutas realmente utilizables con `users.read`, `users.create`, `users.update`, incluidas `/api/users`, `/api/route/users`, suspensión, reactivación, rol, modificación, listas y alternativas indirectas. Verificar que Route Users usa la ruta general donde corresponda; **el cambio de menú no constituye una protección**.
2. Demostrar con pruebas de API directa que **ninguna ruta** permite que `route_manager` vea o modifique fuera de su rama, se modifique a sí mismo, administre pares o superiores, cambie a `route_admin`, o escale privilegios de Core/plataforma.
3. Si las capacidades `users.*` son genéricas sin restricción eficaz, **no asignarlas a `route_manager`**; utilizar la interfaz de administración limitada al dominio Route cuando pueda hacerse con seguridad sin otorgar permisos globales indebidos. Cualquier nueva capacidad o modificación transversal de permisos requiere decisión explícita del PO.
4. Implementar la administración de usuarios, cargo y superior desde el panel existente de Route, usando opciones filtradas en backend y validación independiente al guardar.
5. Documentar S-2 (Core manager→owner) y S-3 (roles `management`) como hallazgos externos al frente; **no** alterar Core ni su política para cerrar silenciosamente esos defectos. Corregir dentro de Route las rutas de escalamiento nuevas o existentes que afecten su delegación.

### B4 — Aplicar scope a todas las experiencias existentes

- **Today / Live** `/admin/route/today`: sujetos visibles, contadores, estado, millas y detalle de acuerdo con la rama actual autorizada.
- **User Activity administrativo** `/admin/route/activity`: listados, filtros y detalles restringidos al conjunto autorizado y, para historia, a sesiones iniciadas bajo el ámbito válido en cada período.
- **Reports y Excel:** exactamente las mismas sesiones/personas/métricas autorizadas; mismo filtro antes de generar agregados o archivos; no aceptar IDs ajenos aunque el usuario conozca la URL.
- **Route Users:** listados y todas las operaciones de usuarios/relaciones, incluidos los endpoints indirectos, con la misma política delegada.
- **Experience de ejecución** `/route/*` y **Activity personal** `/route/activity`: exclusivamente el usuario autenticado, incluso si este es CEO/COO/RM/`route_admin`. No crear selector personal de supervisores.

No crear dashboards nuevos ni cambiar rutas, menús, shell móvil o interfaces aprobadas. Ajustes permitidos: controles mínimos **Cargo** y **Superior** en el formulario administrativo existente; conservar funcionalidad en Web y Mobile.

### B5 — Historia y traslados

1. Registrar vigencias de la cadena para reconstruir pertenencia histórica (incluidos traslados de un superior con toda su rama). No decidir alcance histórico basándose únicamente en la relación actual.
2. **Una WorkSession completa corresponde a la cadena activa en su `started_at`**. No repartir sus viajes y millas por cada cambio de cargo/superior a mitad de turno.
3. La fecha visible del reporte se sigue tomando de `session_date`, mientras que la autorización histórica se compara mediante instantes exactos de vigencia; no usar la zona del navegador o la hora de sincronización offline para atribuir la WorkSession.
4. Cuando una relación anterior es desconocida, **no inferir** quién supervisaba el pasado ni exponer esa historia a nuevos managers. Un superadmin autorizado conserva las consultas permitidas del tenant.
5. El cambio de relación debe reflejarse en la siguiente lectura y no conservar la rama anterior mediante un caché o filtros anteriores.

## 6. Out of Scope / Do Not Change

- No rediseñar la experiencia My Route / Activity / Me, Today / Live, Activity, Reports ni la navegación.
- No modificar Start Work, End Work, P-2, Trips, Activities, geolocalización, odómetro, cálculo de millas, offline o lógica temporal T-1/T-2.
- No aplicar jerarquías de CER ERP o CER Time dentro de Route sin contrato explícito.
- No otorgar permisos extras a OSM o Supervisor ni convertir el cargo en permiso automático.
- No hacer backfill inferido ni reescribir historiales de jornadas.
- No conceder `users.delete` a `route_manager` ni alterar `route_admin` para pasar `test_provisioning_alignment`. La discrepancia reportada (**16 capacidades reales vs. 12 esperadas** en Control A) queda para decisión independiente.
- No fusionar MR ni desplegar en entornos operativos hasta certificación explícita de CER.

## 7. Control C — Pruebas y criterios de aceptación

| ID | Criterio verificable | Evidencia mínima |
|---|---|---|
| AC-01 | `route_manager` creado sin conferir acceso tenant-wide indebido; `route_admin` conserva su contrato | Catálogo/seed, autorización y tests de capacidades |
| AC-02 | CEO/COO/RM ven exclusivamente ramas autorizadas | API directas + UI con al menos dos ramas y dos tenants |
| AC-03 | OSM y Supervisor tienen permisos y self scope idénticos | Comparación efectiva permisos, navegación y lectura personal |
| AC-04 | Niveles opcionales, superior único, sin lateral/ciclos, tenant correcto | Integración y concurrencia / migración |
| AC-05 | Administración delegada respeta niveles y límites de rol, sin self-action ni escalamiento | Operaciones positivas/negativas y auditoría |
| AC-06 | Rutas generales y Route de usuarios no eluden política; sin API lateral de escalamiento | Matriz endpoint × actor × objetivo, incluyendo `/api/users` |
| AC-07 | Traslado RM-A → RM-B preserva historia por WorkSession en su `started_at`, incluida jornada nocturna/traslado a mitad de sesión | Consulta histórica con vigencias e instantes fijados |
| AC-08 | Reports y Excel coinciden exactamente en alcance autorizado; sin filtración en agregados | Resultado API vs. filas reales del Excel |
| AC-09 | Usuarios antiguos sin cargo conservan su Activity propia; managers sin subordinados no ven datos ajenos | Pruebas de compatibilidad y ausencia de backfill |
| AC-10 | Transferencia, revocación, suspensión y cambio de superior se reflejan sin alcance obsoleto | Peticiones consecutivas y trazas de auditoría |
| AC-11 | Vista administrativa y personal permanecen separadas; pantallas sin rediseño | E2E desktop/mobile + capturas |
| AC-12 | Seguridad y regresión de rutas existentes respaldadas por pruebas | Salida de test, fallos clasificados, commit/MR |

### Escenarios obligatorios

1. Organigrama completo CEO → COO → RM → OSM y Supervisor; RM sin OSM; CEO → RM → Supervisor; COO → Supervisor.
2. Dos RM con subordinados distintos, dos tenants, identidades suspendidas y un usuario no asignado.
3. Solicitudes de listado, consulta de ID concreto, update/suspensión, cambio de rol, cambios de superior y exportación usando identificadores de otra rama y de otro tenant.
4. Intentos de CEO/COO/RM de administrar superiores, pares, sí mismos y `route_admin`; intentos de OSM/Supervisor de listar o modificar personal.
5. Transferir supervisor RM-A → RM-B y mover una rama completa; verificar cortes por instante, ausencia de solapes y preservación de WorkSessions históricas.
6. WorkSession que atraviesa medianoche o que contiene el instante de transferencia; toda ella se atribuye al árbol que era vigente en su inicio.
7. CEO/COO/RM operando en `/route/activity` y administración autorizada por separado; self scope no se convierte en tenant scope.
8. Pruebas de concurrencia de dos reasignaciones simultáneas y de sesión revocada / permisos recalculados.
9. E2E Web/Mobile con cinco cargos y Superadmin, dos ramas; capturas antes/después sin nuevos menús.
10. Regresión pertinente de `Today`, Activity, Reports, Users, ejecución personal y permisos, documentando el fallo previo de `test_provisioning_alignment` sin modificar fixture/catálogo para ocultarlo. Distinguir fallos previos, fallos nuevos y pruebas no ejecutadas.

**No conformidad:** un fallo de aislamiento, escalamiento de privilegios, atribución incorrecta de la historia o exposición en Excel **bloquea la certificación del frente**. No etiquetar como “completed” una capacidad de administración delegada que quedó bloqueada por la condición D-1 de `users.*`.

## 8. Entregables requeridos

Entregar **un solo MD final** (actualizando o sustituyendo el informe de Control A sin borrar la evidencia inicial), que contenga:

1. Resumen **AS-BUILT real**: modelos, migraciones, capacidades y APIs finalmente implementadas (no solo diseños).
2. Matriz final cargo → rol → capacidades → scope; OSM = Supervisor demostrable.
3. `Expected → Implemented → Evidence → Gap → Impact` para cada AC; estado **COMPLETED / PARTIAL / BLOCKED / PENDING VALIDATION**.
4. Matriz exhaustiva de rutas administrativas/directas, incluyendo `/api/users` y alternativas, con controles y resultados de casos negativos.
5. Evidencia de migración reversible, una única asignación activa, historial auditable y casos de transferencia.
6. Resultados reales de pruebas de integración, seguridad y E2E Web/Mobile; indicación explícita de pruebas no ejecutadas, fallos preexistentes y nuevos.
7. Evidencia de no regresión de OSM/Supervisor, separación de Activity administrativa/personal y exportaciones.
8. Riesgos/deuda técnica y decisiones no autorizadas evitadas; cualquier bloqueo requiere propuesta acotada de decisión (opciones, riesgos, impacto, recomendación).
9. Branch, SHA(s), MR de código, base usada, estado de merge/deploy y relación con **MR !88** documental. No considerar MR !88 como implementación.

**Definition of Done:** jerarquía operativa, autorización server-side y alcance consistente por rama y por período, exportaciones seguras, delegación sin vías de escalamiento y pruebas verificables. No basta con compilar o mostrar una pantalla correcta. **La certificación final corresponde a CER.**

---

**Instrucción final única:** ejecutar **Control B + Control C**, como fases internas del **mismo desarrollo**, utilizando **solo este archivo como instrucción de implementación**. Las decisiones D-1 a D-4 están cerradas aquí. **Si aparece una necesidad material de nuevas capacidades o cambios globales al Core, no improvisar: bloquear solo esa pieza, documentar el mínimo punto de decisión y mantener el resto en estado verificable.** No fusionar ni desplegar sin certificación expresa de CER.
