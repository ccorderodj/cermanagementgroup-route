# CER Route — Diagnóstico de jerarquía ante cargos vacantes y reemplazos

**Tipo:** instrucción ÚNICA de revisión técnica y funcional — NO autoriza implementar un rediseño.
**Frente:** Role Hierarchy / Roles & Permissions / Users.
**Referencia:** implementación V1.3, MR !90, sobre MR !89 ya integrado a `dev` según el informe de desarrollo.
**Estado:** PENDING DIAGNOSTIC / CER DECISION GATE.

## Context

El Product Owner comprobó en **Edit user** que, al seleccionar **Supervisor**, aparece `Reports to` con personas elegibles (por ejemplo CEO y Regional Manager), pero al seleccionar **COO** el control desaparece o queda vacío. Ocurre especialmente cuando falta el ocupante de un cargo superior. Además, el negocio debe poder **sustituir al ocupante del CEO, COO o RM sin perder ni romper las relaciones jerárquicas** que dependen de su función.

El informe V1.3 declara que:
- CEO es raíz; COO solo puede reportar a CEO; RM puede reportar a CEO o COO; OSM/Supervisor a CEO, COO o RM; Sales directamente a CEO y nunca bajo COO.
- Los roles técnicos diferenciados existen; el cargo se deriva del rol.
- La relación vigente se almacena en `org_assignment.superior_user_id`, apuntando a una persona concreta y con intervalos temporales para historial.
- Se exige un superior ocupante para altas subordinadas y se reconoce bloqueo operativo si no existe CEO cargado.
- Estado operativo y zona horaria no deben modificarse.

**No confundir un campo oculto porque no existen opciones con una falla de persistencia o una caída:** reproducir y determinar la causa con evidencia.

## Objective

Investigar y proponer una solución verificable para que el catálogo de roles permanezca seleccionable, `Reports to` tenga comportamiento claro aun cuando haya cargos superiores vacantes, y los reemplazos de personas en cargos de mando no rompan la estructura, la visibilidad, el historial ni las reglas de seguridad.

## Confirmed business requirements

1. El organigrama debe soportar reemplazo de ocupantes sin tener que reconstruir manualmente la cadena organizacional.
2. La ausencia temporal del ocupante de CEO, COO o RM no debe hacer desaparecer ni corromper la estructura lógica de la compañía.
3. Sales depende directamente del cargo CEO, utiliza solo funciones operativas propias y nunca es visible para COO/RM por ese hecho.
4. Roles y alcance administrativo deben continuar respetando tenant, permisos efectivos y jerarquía autorizada.
5. Los roles empresariales aprobados son CEO, COO, Regional Manager, OSM, Supervisor y Sales, además del Superadmin Route fuera del árbol.
6. No modificar Estado operativo, Zona horaria, cálculos de horario, Routing, Mileage, WorkSessions, Activity ni el diseño general de navegación.

## Stage 1 — AS-BUILT investigation (read-only, obligatory)

1. Identificar commit, rama y migraciones activas del entorno reproducido; distinguir `dev`, MR !90 y despliegue. Registrar evidencia de versión frontend/backend.
2. Reproducir **Edit user** con Supervisor y COO con estos estados: CEO existente/activo; CEO ausente; CEO inactivo; CEO sin `org_assignment` vigente; COO existente sin CEO; COO reemplazado; RM bajo COO vacante. Diferenciar ausencia del campo, campo deshabilitado, opciones vacías, errores de API y errores JS.
3. Analizar `SecurityUserForm`, opciones de `Reports to`, `RouteOrganization`, hooks o condiciones de render, API `/api/route/organization/options`, validaciones de `PUT /api/users/{id}` y `/api/route/users/{id}`, ruta de delegación y control de datos obsoletos tras recarga.
4. Examinar qué ocurre al desactivar, retirar, cambiar rol o reemplazar al CEO, COO o RM cuando hay subordinados directos e indirectos. Documentar transacción, errores, filas históricas, referencias activas, auditoría y visibilidad efectiva.
5. Verificar si existe hoy un concepto de **posición organizacional persistente** independiente de la persona, o únicamente `org_assignment` por usuario + `superior_user_id`. Confirmar restricciones de unicidad sobre ocupantes (por ejemplo uno o varios CEO por tenant); no inferirlo del nombre del rol.
6. Comprobar el alcance Today (vigente), Activity/Reports/Excel (histórico por `WorkSession.started_at`), Users y ambos montajes de API. Probar Sales vs COO y cambios efectivos tras reemplazo.
7. Identificar cómo afecta el período de supervisión aprobado (D-3) a un reemplazo: responsable anterior, nuevo responsable y jornadas previas; **no cambiar la política histórica sin decisión de CER**.

## Stage 2 — Architecture alternatives and impact

Comparar como mínimo:

**A. Relación directa usuario → superior_user_id**, corregida con transferencia transaccional. Analizar si permite períodos vacantes sin bloquear altas o introducir vínculos ficticios; costo y riesgo de migrar cada subordinado al reemplazar un superior; auditoría e historial.

**B. Estructura estable de puestos/nodos organizacionales + ocupación temporal por usuario**. Relación del puesto hijo con puesto padre dentro del mismo tenant, con ocupante opcional. Roles RBAC siguen siendo capacidades del usuario: una plaza vacante no concede acceso a nadie. Considerar varias plazas del mismo tipo, por ejemplo distintos RM o supervisores. Evaluar migración del modelo actual, integridad y autorización por ocupación vigente.

**C. Alternativa equivalente** si existe un mecanismo ya implementado que evita duplicación de datos, con justificación verificable.

Para cada opción incluir ventajas, riesgos, migración y reversión, impacto a APIs/frontend, consistencia histórica, seguridad, pruebas y esfuerzo estimado. Recomendar una sola, **sin implementarla**.

## Mandatory scenarios / expected behavior to analyze

| Caso | Comportamiento de negocio esperado |
|---|---|
| Seleccionar COO sin CEO ocupante | COO debe seguir siendo rol elegible. La UI no puede ocultar silenciosamente `Reports to`: debe señalar de forma clara si la asignación queda pendiente o bloqueada, según solución aprobada. |
| CEO queda vacante | La estructura de COO, RM y Sales permanece registrada, sin transferir automáticamente permisos del CEO a COO. |
| Reemplazo CEO-A → CEO-B | Las relaciones de puestos se mantienen, el usuario saliente pierde autoridad vigente y el entrante la recibe sólo desde su asignación autorizada; política histórica pendiente de confirmación. |
| Reemplazo COO-A → COO-B | RM/OSM/Supervisor permanecen en rama operativa y no se exponen a Sales; no se recrean usuarios ni jornadas. |
| RM sin ocupante | Los equipos continúan asociados a la posición del RM sin perder sus registros ni cambiar automáticamente de superior funcional. |
| Sales bajo CEO | Ningún COO/RM puede ver Sales por consultas de Today, Activity, Reports, Excel, Users ni acceso directo por ID. |
| Tenant A vs tenant B | Ningún cargo ni ocupante puede usarse como padre en otro tenant. |
| Cambios concurrentes | Sin ciclos, sin vínculos cruzados, con versionado/transacciones y auditoría. |

**Nota:** que un cargo vacante permita nuevas altas, quién administra esos puestos y si puede haber múltiples CEO son **DECISION REQUIRED**; formular propuesta, no asumir aprobación. Igualmente, definir si el CEO entrante ve historia anterior al inicio de su cargo requiere decisión expresa, respetando por defecto D-3.

## UI/UX diagnostic output

Describir una experiencia mínima compatible con `Edit user`: rol/cargo siempre visible, relación `Reports to` persistente y explicación de situación vacante o sin candidato. No crear mockups nuevos ni nuevas páginas en esta etapa. Separar claramente: rol del usuario, puesto organizacional, ocupante actual y puesto superior. Evitar añadir campos innecesarios en la operación diaria.

## Security / audit invariants

- Autorización **server-side**: rol y relación organizacional son condiciones conjuntas, no suficientes aisladamente.
- Separación de tenant; mínimo privilegio; ningún acceso de COO a Sales; ausencia de superior no significa `tenant-wide`.
- Revocación efectiva inmediata del cargo para ocupante saliente; sin autoconcederse CEO ni saltos de nivel.
- Historial inmutable y atribuible al momento de `WorkSession.started_at`, salvo aprobación distinta del PO.
- Registrar actor, fecha, cargo anterior/nuevo, reemplazo, motivo y versiones; movimientos transaccionales.
- Mantener Core transversal sin cargar lógica de estructura empresarial de Route.

## Out of scope

- NO programar, migrar datos, fusionar MR, desplegar, modificar roles/capacidades ni crear una tabla todavía.
- NO tocar configuración de Estado/Zona Horaria o reglas GPS/Routing/millaje.
- NO alterar la política de Sales, permisos operativos, navegación ni registros existentes.

## Deliverable — one MD report

Nombre: `CER_ROUTE_HIERARCHY_VACANCY_REPLACEMENT_AS_BUILT_DIAGNOSTIC_001.md`.

El informe debe incluir, de manera concisa pero verificable:

1. **Reproducción y causa raíz** exacta del campo que desaparece, con SHA, entorno, ruta y evidencia (API/JS/UI). Distinguir CONFIRMED de hipótesis.
2. **Modelo AS-BUILT** con tablas, claves, restricciones, servicios y rol/cargo/relación.
3. **Matriz de escenarios** CEO/COO/RM presentes, vacantes, desactivados y reemplazados; `Expected → Implemented → Evidence → Gap → Impact`.
4. **Opciones A/B/C** con recomendación arquitectónica, impactos, estimación y migración / rollback.
5. **Puntos de decisión CER**, especialmente: vacancias permitidas, número de plazas CEO, acceso histórico del sucesor y autorización de reemplazos.
6. **Plan de pruebas** posterior: unitarias, integración, permisos API, aislamiento, concurrencia, regresión, Web/Mobile y datos históricos.
7. Referencias a archivos/líneas, evidencia de consola/red y capturas de los dos estados del formulario.

**Gate:** entregar diagnóstico, detenerse y esperar aprobación del Product Owner sobre la arquitectura y las reglas de reemplazo. No declarar la jerarquía certificada mientras la ausencia de ocupantes impida administrar relaciones de manera segura.
