# CER Route — Cierre de jerarquía con roles diferenciados y superior por usuario

**INSTRUCCIÓN ÚNICA V1.3 — corrección del frente de jerarquía / MR !89**  
**Destinatario:** programador y agente de CER Route  
**Fecha:** 13 de octubre de 2026  
**Estado:** autorizada para verificación puntual, implementación y pruebas dentro del alcance descrito  
**Evidencia de referencia:** `CER_ROUTE_ROLE_HIERARCHY_RBAC_DATA_SCOPE_IMPLEMENTATION_REPORT.md`; capturas del PO de Roles & Permissions, Edit user y designación de supervisores.

> **Este es el único documento ejecutable para el ajuste pendiente del frente. Sustituye la instrucción correctiva V1.2 en todo lo relativo al trabajo futuro.** Conserva las reglas previamente aprobadas de aislamiento, jerarquía histórica, autorización y compatibilidad que no contradigan V1.3. No abrir otro checkpoint, ni hacer merge o deploy sin autorización de CER.

## 1. Decisión expresa del Product Owner

1. **Crear roles de CER Route separados y reconocibles**: **CEO, COO, Regional Manager, OSM, Supervisor y Sales**, cada uno seleccionable por su nombre en la administración de usuarios y visible en Roles & Permissions. **No** usar `Route Manager` como único rol visible para CEO, COO y Regional Manager.
2. Crear/usar una **relación de superior (parent) por usuario**: al editar un usuario, el administrador elegirá su rol organizacional y **a qué usuario reporta**. La aplicación deberá mostrar y guardar esa relación. Una relación permitida entre *tipos de rol* no sustituye la asignación a una persona concreta.
3. **Sales usa CER Route** para su jornada, viajes, visitas y Activity propia. Su superior directo debe ser un **CEO**; no puede quedar dentro del ámbito de COO o Regional Manager, ni recibir permisos administrativos.
4. **OSM y Supervisor tienen diferentes nombres de rol, pero exactamente las mismas capacidades y el mismo nivel de acceso**. No existe relación de subordinación lateral entre ellos.
5. **No modificar absolutamente nada relacionado con Estado de operación ni Zona horaria.** La detección automática de zona no solucionó el problema del PO; la configuración actual queda **intacta**, aunque parezca redundante. No ocultar, eliminar, reordenar ni cambiar sus selectores, validaciones, valores, persistencia o lógica. No tocar T-1/T-2, UTC, IANA, DST, `session_date`, formatos horarios ni reportes temporales. **El alcance de esta instrucción es únicamente roles, jerarquía, edición de usuarios y permisos.**

## 2. Context / AS-BUILT a verificar antes de editar

El informe del MR !89 afirma que existen `org_assignment` (cargo, `superior_user_id`, vigencias), `route_manager` con permisos de mando, política de lectura por descendientes y controles `Position` / `Reports to` dentro de `SecurityUserForm.tsx`. Sin embargo, CER observa:

- El formulario **Edit user** utilizado en la aplicación no ofrece visiblemente **CEO / COO / Regional Manager / OSM / Sales ni Reports to**; sólo ofrece roles genéricos.
- La pantalla **Roles & Permissions** muestra `Route_manager` como un rol genérico y, en la captura, con **0** capacidades, contradiciendo el reporte que afirma nueve.
- La pantalla de supervisores muestra Estado y Zona horaria, pero **no** constituye la edición de jerarquía solicitada.
- El informe declaró MR !89 pendiente de integración/despliegue; no asumir que las capturas pertenecen al mismo SHA o a la versión nueva.

**Verification Gate — obligatorio, limitado y de solo lectura antes de modificar**: identificar rutas reales y formulario que usa el PO; comprobar SHA/bundle/backend/DB/migración `0017`, rol `route_manager` y permisos efectivos en el tenant; identificar si `Position` / `Reports to` están en otro formulario, ocultos por permisos, no desplegados o desconectados. Documentar causa concreta. El análisis no constituye otro entregable ni impide implementar lo ya autorizado. No ejecutar migraciones/despliegues en el entorno operativo sin aprobación.

## 3. Objective

Que un administrador autorizado pueda **crear o editar un usuario desde el flujo real de Users de CER Route**, seleccionar explícitamente su rol organizacional, seleccionar su superior autorizado y comprobar que las pantallas y APIs únicamente muestran la información de sus subordinados. La configuración debe funcionar para dos ramas simultáneas e independientes: **Operaciones** y **Sales directo a CEO**.

La configuración y las autorizaciones deben funcionar sin saber qué código técnico corresponde al cargo, sin pantallas administrativas paralelas y sin intervenir la configuración del estado o la zona horaria.

## 4. Jerarquía y padres permitidos — contrato funcional

| Rol visible de CER Route | Parent permitido al asignar un usuario | Capacidades y alcance |
|---|---|---|
| **CEO** | Raíz organizacional, sin superior Route obligatorio | Lectura y administración de **sus descendientes**, no acceso general al tenant por ser CEO |
| **COO** | CEO | Lectura y administración de su rama subordinada; nunca Sales de la rama paralela del CEO |
| **Regional Manager** | COO **o CEO** (COO es nivel opcional) | Lectura y administración de su rama subordinada |
| **OSM** | Regional Manager, COO **o CEO** (niveles intermedios opcionales) | Sólo ejecución y Activity personal, sin administración ni datos ajenos |
| **Supervisor** | Regional Manager, COO **o CEO** | Exactamente los mismos permisos que OSM; sólo lo propio |
| **Sales** | **CEO directo, exclusivamente** | Sólo ejecución y Activity personal; sin administración ni acceso a terceros |

**Superadmin (`route_admin`)**: permanece como función privilegiada de CER Route, **fuera del árbol organizacional** y con su comportamiento autorizado vigente, sin convertirse automáticamente en CEO. Roles de Core (`owner`, `admin`, `manager`, `viewer`) se conservan y no se reinterpretan como cargos Route.

**Distinguir dos conceptos:**
- **Parent role / regla estructural:** conjunto de tipos de rol elegibles para ser superior; valida niveles y ramas, **no** transfiere permisos por herencia.
- **Reports to / parent user:** identificador del usuario concreto elegido como superior vigente dentro del mismo tenant. Este dato es el que construye el árbol real y determina Data Scope.

Si la arquitectura existente ya representa el parent en `org_assignment.superior_user_id`, **reutilizarla**. No introducir tabla de roles heredados ni duplicar el árbol por comodidad. La lista permitida de tipos de parent puede implementarse en la política de dominio existente, con validación server-side. No crear relaciones implícitas ni adivinar el superior por el rol o estado geográfico.

**Ejemplo obligatorio de prueba:** CEO-A tiene COO-A → RM-A → Supervisor-A y, en paralelo, Sales-A **directamente** bajo CEO-A. CEO-A ve ambos; COO-A y RM-A no ven Sales-A ni sus métricas en ninguna superficie. Los supervisores/OSM/Sales ven sólo su actividad propia.

## 5. Roles, capacidades y compatibilidad

### FR-01 — Crear roles diferenciados

Provisionar en cada tenant de Route los roles identificables **CEO**, **COO**, **Regional Manager**, **OSM**, **Supervisor** y **Sales**. Los códigos internos pueden seguir las convenciones del catálogo actual, pero su **nombre visible no debe ser un único `route_manager`**. No afectar la identidad global ni crear esos roles en el Core de otros productos.

- CEO, COO y RM: conjunto de capacidades actualmente aprobado para `route_manager` (ejecución personal, listas, Today, Activity admin, Reports, exportación y administración delegada de usuarios), **con Data Scope obligado por la jerarquía** en todas las APIs.
- OSM, Supervisor y Sales: **idéntico conjunto operativo mínimo existente del Supervisor** (Start/End Work, viajes/actividades, valores y Activity propia), sin capacidades de lectura/administración de otras personas.
- No permitir que `Roles & Permissions` conceda accidentalmente privilegios globales al configurar alguno de estos roles. Investigar el significado de `Role.category`: si `management` implica aprobación de permisos en el núcleo, **no usarlo para roles de negocio sin las salvaguardas pertinentes**.
- El rol `route_admin` se mantiene, y no se amplían privilegios `owner/admin/manager` del Core.
- Sin asignaciones de rol ficticias. En usuarios existentes con `route_manager` o `supervisor`, **no inferir ni reasignar automáticamente el nuevo cargo**. Ofrecer transición explícita y autorizada desde Edit user; mientras haya legado, conservar un scope al menos igual de restrictivo, nunca tenant-wide.
- Durante migración/provisioning de roles, verificar que el catálogo de capacidades **se alinea realmente** en el tenant; no basta crear filas de roles vacías. Evidenciar conteos y, sobre todo, **las capacidades efectivas** (el reporte afirma `route_manager=9`, la captura muestra 0). No cambiar los números de pruebas sin justificar diferencias de producto.

### FR-02 — Roles y superior en Edit user, en la pantalla real

Alinear/reutilizar el formulario de Users desde el que CER edita usuarios; debe ofrecer de forma clara:

1. **Rol de CER Route**: CEO / COO / Regional Manager / OSM / Supervisor / Sales (además del manejo especial de superadmin para usuarios autorizados).
2. **Reports to / Superior**: selección de usuario del mismo tenant, filtrada por reglas de parent y por alcance de administración; mostrar el nombre de la persona, no sólo el identificador. CEO puede establecerse como raíz.
3. **Relación vigente** al editar, persistente tras guardar, recargar y volver a abrir.

Reutilizar los campos/servicios existentes de `org_assignment`, sus vigencias históricas, concurrencia y auditoría. No dejar `Role` y `Position` como **dos controles editables contradictorios** en Route: el cargo organizacional y el rol visible deben corresponderse de forma determinística y validada desde servidor. Si sigue existiendo una columna `position` por compatibilidad, mantenerla coherente con el rol seleccionado sin borrar el historial.

El usuario no podrá guardar un rol que requiere superior sin seleccionar una persona elegible; no sustituir por un `route_manager` genérico ni por un parent escogido automáticamente. **Sales sólo puede seleccionar un CEO**: CEO inactivo, otro tenant u otra posición → rechazo. Si no hay CEO elegible, error claro y sin cambios parciales.

Evitar reconstruir toda la UI de seguridad o crear una pantalla nueva. Si se trata de distintos formularios de Core y Route, documentar cuál gobierna cada uno y garantizar que la entrada habitual de **Users de Route** muestre los campos requeridos con los permisos correctos. No modificar los selectores de Estado/Zona horaria de otra pantalla.

### FR-03 — Administración delegada y validación de parent

- `route_admin` autorizado puede configurar la jerarquía dentro de su tenant.
- CEO gestiona sólo descendientes y puede asignar COO/RM/OSM/Supervisor/Sales; **Sales siempre bajo CEO directo**, nunca por interposición de COO.
- COO puede gestionar subordinados RM/OSM/Supervisor de su rama; **no puede asignar, crear, editar, convertir, mover o leer Sales**, aunque adivine un ID o invoque `/api/users`.
- RM gestiona únicamente subordinados OSM/Supervisor de su rama; no Sales ni otros RM, COO o CEO.
- OSM, Supervisor y Sales no administran usuarios ni roles, aunque manipulen las llamadas API.
- Nadie puede colocarse como propio superior, crear ciclos, colgarse de un par/subordinado, saltar de tenant, modificar un superior fuera de su ámbito ni autoelevarse de privilegio.
- Revalidar autorización **sobre actor, usuario objetivo, rol nuevo, parent nuevo y rama resultante** en cada escritura; validar de manera atómica para impedir cambiar sólo rol o sólo parent si el conjunto quedara inconsistente.
- Conservar periodos de vigencia aprobados. En cambios de superior o rol no inventar relaciones históricas ni reescribir WorkSessions, Trips o Activities.
- Audit trail: quién, cuándo, usuario, rol previo/nuevo, superior previo/nuevo, motivo cuando corresponda.

### FR-04 — Data Scope, no sólo menú

Aplicar una política única o reutilizar la ya implementada para autorizar todos los accesos administrativos: Today/Live, Activity administrativa, Reports, Excel/exports, listados de usuarios, opciones de superior, endpoints de organización y lecturas/ediciones por ID. Filtrar **antes** de agregar. Restringir tanto los endpoints Route como **las rutas compartidas `/api/users`** que consumen las mismas capacidades.

- CEO: sólo descendientes de su árbol (incluido Sales directo).
- COO y RM: sólo sus descendientes; nunca Sales paralelo bajo CEO.
- OSM/Supervisor/Sales: sin lectura administrativa; `/route/activity` exclusivamente propia.
- `route_admin`: su alcance autorizado actual, sin cambios.
- Tenant isolation: obligatorio en servidor para listados, detalles, agregados y exports; no basta ocultar opciones UI.
- Historial: preservar regla ya aprobada de visibilidad por periodos de relación y `WorkSession.started_at`; no mezclar historia de la otra rama. **No modificar interpretaciones temporales ni zona horaria.**
- Respuestas para objetivos fuera de alcance deben conservar la semántica segura de 403/404 ya definida; nunca filtrar detalles sensibles por el mensaje de error.

### FR-05 — Habilitación de ejecución de roles operativos

Sales, OSM y Supervisor deben poder acceder a My Route y su Activity propia de acuerdo con el modelo existente de ejecutor. Revisar la relación real entre rol, `SupervisorProfile`, designación de ejecutor y vehículo: crear una cuenta con Sales no debe dar permisos administrativos ni dejar una cuenta ejecutora sin los requisitos conocidos de activación. Reutilizar provisioning existente, sin introducir CRM, módulos Sales nuevos, permisos de flota ni flujos de viaje distintos.

## 6. No scope / Do Not Change — estricto

**No modificar:**

- **Zona horaria**: no cambiar zona IANA, override, detección del dispositivo, captura offline, `start_time_zone`, offsets, DST, visualización de horas ni lógica de fecha operativa.
- **Estado operativo**: no cambiar su catálogo, selector, visibilidad, validación, persistencia, derivación ni disposición. **No intentar derivar zona horaria del estado**.
- `Start Work`, `End Work`, odómetros, Keep working, trips, mileage, actividad, RTE08, H-1/H-3, reportes de kilometraje y flujos offline.
- Roles y permisos transversales del Core ajenos a CER Route; cuentas superadmin fuera de las transiciones autorizadas.
- Navegación y pantallas de ejecución, ni inventar un dashboard para cada cargo.
- Datos históricos y relaciones previas por backfill adivinado; migraciones destructivas.
- Merge/deploy a producción sin autorización del Product Owner.

Si un cambio solicitado exige inevitablemente modificar alguno de estos elementos, **detener ese cambio concreto y presentar un bloqueo con evidencia y alternativa mínima**, sin extender por cuenta propia el alcance.

## 7. Acceptance Criteria

| ID | Criterio verificable |
|---|---|
| AC-01 | Verificación de **pantalla real**: identificar por qué Cargo / Reports to no se mostraba, con rutas y SHA front/back/DB; evidencia antes/después. |
| AC-02 | En Roles & Permissions aparecen roles diferenciados CEO, COO, Regional Manager, OSM, Supervisor y Sales, con capacidades realmente efectivas y sin privilegios de Core. |
| AC-03 | Edit user permite seleccionar uno de esos roles y un **superior concreto** conforme a matriz; guardar, reabrir y recargar mantiene la relación. No se exige manejar `route_manager` genérico. |
| AC-04 | CEO→COO→RM→Supervisor y CEO→Sales se configuran en el mismo tenant; COO y RM jamás ven Sales, CEO autorizado sí; superadmin sigue según alcance vigente. |
| AC-05 | Intentos por API de dar Sales a COO/RM, crear `Sales→COO`, asignar parent de otra compañía, ciclo o elevación de rol se rechazan sin cambios parciales. |
| AC-06 | OSM y Supervisor son roles separados por nombre **pero idénticos en capacidades y scope**, también Sales tiene acceso operativo equivalente sin administración. |
| AC-07 | Todas las superficies Today/Activity/Reports/Excel/Users y endpoints generales/Route filtran por alcance; contadores y export no fugan otras ramas. |
| AC-08 | Transferencias y cambios de rol mantienen vigencia histórica, auditoría y ausencia de acceso retroactivo indebido; permisos se actualizan en la siguiente petición. |
| AC-09 | No se modifica **ninguna** funcionalidad o UI de Estado de operación ni Zona horaria; probar ausencia de diffs/migraciones temporales y regresión de pantallas existentes. |
| AC-10 | No se reasignan sin autorización usuarios previos; `route_manager` legado no habilita acceso total; roles nuevos se provisionan/alinean con idempotencia y no generan cuentas huérfanas. |
| AC-11 | Funciona en escritorio y móvil con captura real de Roles & Permissions y Edit user, sin cambios en las pantallas operativas; Sales ejecuta y sólo ve lo suyo. |
| AC-12 | Migración reversible y suite focalizada de seguridad, integración y E2E aprobada; regresión reportada con fallos previos/nuevos y pruebas no ejecutadas expresamente identificadas. |

## 8. Tests Required

- Provisioning/migración tenant existente y tenant nuevo: seis roles distintos, permisos mínimos correctos, roles preexistentes intactos, sincronización de capacidades e idempotencia; downgrade seguro o limitación informada.
- Comparación exacta del conjunto efectivo OSM vs Supervisor y Sales; CEO/COO/RM con igualdad de capacidades funcionales, **distintos scopes por la jerarquía**.
- Roles y superiores en formulario real, selección de parent permitida, cambio de rol que invalida el parent existente, validación y reversión atómica, refresh/nueva sesión; desktop y móvil.
- Dos CEOs o varios candidatos (nunca elección implícita), CEO sin subalternos, Sales sin CEO, COO con RM directo, RM directo de CEO, Supervisor bajo COO sin RM, intento OSM→Supervisor, ciclos y tenants distintos.
- Seguridad por ruta y actor: Today, Activity, Reports, Excel, Users por `/api/users` y `/api/route/users`, `/api/route/organization`, por ID directo, listados y contadores. COO/RM deben recibir 403/404/ausencia ante Sales.
- Historial de traslados RM-A→RM-B; Sales asignado/desasignado sin fuga histórica; cambios de rol y parent con auditoría.
- Ejecución Sales: Start Work, Trip, Activity, My Activity; requerimientos existentes de designación y vehículo; ausencia de acceso al menú/admin y API de administración.
- Evidencia de **cero cambios** a estado y zona horaria, DST, serialización de timestamps y sus controles visibles; regresión limitada de Start/End Work para detectar interferencias.
- Comparar contra la línea base y documentar si continúa `test_provisioning_alignment` u otros fallos existentes, sin alterar pruebas para esconder discrepancias.

## 9. Deliverables / Gate de certificación

Entregar **un único MD final actualizado** con:

1. Inventario `Expected → Implemented → Evidence → Gap → Impact` por AC01–AC12, etiquetando COMPLETED / PARTIAL / BLOCKED / PENDING VALIDATION.
2. Evidencia del Verification Gate: pantallas reales, rutas, SHA/frontend/backend, revisión de `0017` y causa del rol `route_manager` sin permisos en la captura.
3. Esquema y catálogo final: nombres/códigos efectivos de los seis roles, capacidades y parent roles permitidos, cómo se guarda **Reports to** por usuario, y tratamiento de usuarios legados.
4. Matriz de seguridad actor×objetivo×API (positivo/negativo) con COO/RM no viendo Sales, incluyendo listados/agregados/exportación e intentos directos por ID.
5. Capturas reales de Roles & Permissions, Edit user con Role + Reports to y árbol CEO→(COO→RM→Supervisor, Sales), tanto desktop como móvil.
6. Pruebas de ejecución propia para Sales/OSM/Supervisor; pruebas E2E e integración; resultados de suite y regresiones.
7. Evidencia por diff de **Estado/Zona horaria intocados**; migración y pasos seguros de provisioning/rollback; auditoría; SHAs, MR y estado merge/deploy.

**Definition of Done:** desde la UI realmente utilizada, CER puede asignar cada rol por su nombre, establecer el superior concreto y observar la visibilidad jerárquica correcta. Sales depende directamente del CEO y nunca aparece al COO/RM. OSM y Supervisor son funcionalmente equivalentes. No se modifican Estado ni Zona horaria. El código y tests en rama no sustituyen la validación de CER; no fusionar/desplegar sin autorización.
