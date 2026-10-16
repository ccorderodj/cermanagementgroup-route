Instrucción para el agente del programador — Preflight de jerarquía, roles y data scope CER Route
Objetivo
Analiza el estado actual de CER Route y recomienda la mejor forma de incorporar el nuevo modelo jerárquico de usuarios, roles, permisos y alcance de datos.
No implementes cambios todavía.
Queremos recibir primero:
- diagnóstico del baseline actual;
- impacto sobre lo ya construido;
- arquitectura recomendada;
- decisiones técnicas propuestas;
- decisiones de producto que realmente falten;
- checkpoints recomendados;
- riesgos;
- estimación de esfuerzo/tiempo.
Usa como evidencia primaria el repositorio actual y las entregas certificadas, especialmente RTE02-A02 y los módulos posteriores que dependan de autorización o tenant scope.
Requerimiento funcional confirmado por CER
La jerarquía funcional requerida es:
Superadmin
    ↓
CEO
    ↓
COO
    ↓
RM
    ↓
OSM
    ↓
Supervisor

La jerarquía admite niveles omitidos donde CER lo ha definido. En particular:
COO
 ├── RM
 │    ├── OSM
 │    │    └── Supervisor
 │    └── Supervisor
 │
 └── OSM          ← permitido si no existe RM
      └── Supervisor

No asumas todavía otras combinaciones no indicadas; si técnicamente necesitas definirlas, identifícalas como decisión pendiente.
1. Superadmin
Debe poder:
- ver todo CER Route;
- editar todo CER Route;
- administrar usuarios;
- administrar roles permitidos por CER Route;
- administrar relaciones jerárquicas;
- administrar catálogos;
- administrar configuración;
- ejecutar funciones operativas cuando corresponda.
Analiza si el actual route_admin puede evolucionar de forma compatible a esta función o si existe una razón técnica real para introducir otro rol.
No cambies el Platform Superadmin/Core Superadmin sin necesidad.
2. CEO
Debe tener:
- visibilidad sobre la organización por debajo de él;
- capacidad de administrar relaciones jerárquicas;
- administración de catálogos;
- administración del personal dentro de su alcance;
- capacidad Execute.
No debe asumirse automáticamente que tiene autoridad fuera de su tenant.
Determina qué capacidades existentes pueden reutilizarse y cuáles nuevas serían necesarias.
3. COO
Debe:
- visualizar RM, OSM y Supervisores dentro de su estructura;
- administrar RM;
- administrar OSM;
- administrar Supervisores;
- administrar las relaciones jerárquicas entre ellos;
- administrar asignaciones de roles/permisos dentro del alcance autorizado;
- tener Execute.
Regla jerárquica confirmada:
COO → RM → OSM → Supervisor

pero:
COO → OSM

es válido cuando ese OSM no pertenece a un RM.
Requerimiento explícito del tomador de decisiones: el COO debe poder administrar estas relaciones de usuarios, roles/permisos y jerarquía.
Analiza cuidadosamente cómo implementar esto sin permitir escalamiento hacia CEO, Superadmin, Core roles ni usuarios fuera de su scope.
4. RM
Debe:
- visualizar OSM y Supervisores dentro de su alcance;
- administrar OSM;
- administrar Supervisores dentro de su alcance;
- tener Execute.
Debe quedar impedido de administrar usuarios superiores, otros RM, COO, CEO o Superadmin salvo que CER apruebe posteriormente otra regla.
5. OSM
Debe tener:
- visibilidad;
- Execute.
Determina, a partir del modelo funcional y del baseline, qué debe significar exactamente su visibilidad cuando tenga Supervisores debajo.
No inventes capacidad Manage para OSM si el requerimiento no la exige.
Si necesitas una decisión CER para determinar si OSM puede ver únicamente sus Supervisores o además administrarlos, identifícala claramente.
6. Supervisor
Debe tener:
- visibilidad de su propia operación;
- Execute.
Mantener como principio:
scope = SELF

salvo decisión CER diferente.
No ampliar administración.
Conceptos que debes separar
No mezcles:
ROLE / CAPABILITY
¿Qué puede hacer?

con:
DATA SCOPE / HIERARCHY
¿Sobre quién puede hacerlo?

Analiza si la mejor arquitectura es:
RBAC + hierarchical data scope

en lugar de codificar toda la jerarquía dentro de los roles.
La autorización debe seguir siendo server-side.
El frontend nunca debe decidir por sí solo qué subordinados puede consultar o administrar un usuario.
Administración de roles y permisos
El requisito de que CEO/COO puedan administrar personal y que COO administre relaciones de permisos/roles debe analizarse con especial cuidado.
No asumas automáticamente que CER requiere un editor libre de capabilities.
Distingue entre:
A. Administración de asignaciones
- asignar CEO/COO/RM/OSM/Supervisor;
- cambiar rol;
- asignar superior;
- reasignar estructura;
- activar/desactivar;
- consultar historial.
y:
B. Administración del contenido del rol
- agregar/quitar capabilities al rol COO;
- modificar qué significa RM;
- crear roles arbitrarios.
Evalúa ambas.
Recomienda la opción más segura y mantenible para el requisito actual.
Si A satisface el requerimiento sin introducir un editor dinámico de permisos, indícalo expresamente.
Si consideras indispensable B, explica por qué y qué impacto tendría.
Effective dating e historial
Evalúa si las relaciones jerárquicas deben manejarse con vigencia histórica:
effective_from
effective_to

La recomendación CER actual es preservar historial y evitar reemplazos destructivos.
Ejemplo:
Supervisor X
Jan–Jun → OSM A
Jul–... → OSM B

Analiza:
- impacto sobre reportes históricos;
- reglas de solapamiento;
- reasignaciones;
- usuarios desactivados;
- cambio de rol;
- cambio de parent;
- consistencia histórica.
Reglas de seguridad a considerar
La propuesta debe impedir al menos:
- cross-tenant assignments;
- self-escalation;
- asignar un superior de menor nivel;
- ciclos jerárquicos;
- múltiples relaciones activas incompatibles;
- que COO se convierta a sí mismo en CEO/Superadmin;
- que RM administre otro RM;
- que OSM/ Supervisor accedan a administración no concedida;
- utilizar /api/users Core para saltarse las restricciones de CER Route;
- asignar roles Core desde CER Route;
- confiar en un scope enviado por el cliente.
Revisa especialmente los controles introducidos en RTE02-A02 para no reabrir bypasses ya corregidos.
Compatibilidad
Analiza impacto sobre:
- RTE02 Users / Roles;
- RTE03 Work Sessions;
- RTE04 Trips / Odometer;
- RTE05 Activities;
- RTE06 Location / Mileage;
- futuras vistas Today/Live;
- Activity;
- Reports.
El objetivo es que RTE03–RTE06 necesiten como máximo adaptación de autorización/regresión, no rediseño funcional.
Identifica cualquier excepción.
No implementar todavía
Este trabajo es exclusivamente de análisis.
No:
- crear migraciones;
- agregar roles;
- modificar capabilities;
- crear UI;
- cambiar APIs;
- alterar RTE03–RTE06;
- comenzar RTE07.
Entrega requerida
Devuelve un único análisis estructurado de la siguiente manera:
A. Current State
Describe el modelo actual real:
- roles Route existentes;
- capabilities;
- /api/route/users;
- relación con Core roles;
- restricciones de asignación;
- autorización;
- tenant scope;
- componentes reutilizables.
No repitas documentación completa. Resume solo lo relevante para esta modificación.
B. Gap Analysis
Compara:
modelo actual
vs.
Superadmin → CEO → COO → RM → OSM → Supervisor

Identifica exactamente qué no existe.
C. Recommended Functional Model
Propón una matriz clara:
Role
Read
Execute
Manage Users
Manage Hierarchy
Manage Catalogs
Manage Role Assignments
Data Scope

Utiliza los requerimientos CER anteriores como restricciones.
No agregues autoridad funcional sin indicarla como recomendación.
D. Recommended Hierarchy Model
Define técnicamente cómo recomiendas representar:
- parent/child;
- niveles;
- relaciones opcionales;
- effective dating;
- descendants;
- self;
- full-tenant;
- historial.
No impongas una solución excesiva si el baseline permite algo más simple.
E. Permission / Scope Architecture
Recomienda cómo separar:
capability
+
data scope

y cómo futuros módulos deberían consumir el resolver de scope sin duplicar lógica.
F. Role Administration Recommendation
Explica concretamente qué significa que COO pueda administrar roles/permisos.
Compara brevemente:
- asignación controlada de roles;
- editor dinámico de capabilities.
Recomienda cuál implementar ahora y por qué.
G. UX Impact
Indica qué cambios serían necesarios en:
- Users;
- role selector;
- hierarchy administration;
- relationship changes;
- history;
- visibility according to role.
No diseñes pantallas completas todavía.
H. Security Analysis
Incluye:
- privilege escalation;
- tenant isolation;
- upward/downward administration;
- direct API bypass;
- cycle prevention;
- effective-dating overlap;
- audit;
- least privilege.
I. Compatibility / Regression Impact
Clasifica el impacto sobre RTE02–RTE06 como:
No impact
Regression only
Adaptation required
Functional redesign required

y explica únicamente donde exista impacto real.
J. Decisions Required from CER
No conviertas decisiones técnicas ordinarias en preguntas.
Devuelve únicamente decisiones que realmente necesiten Product Owner.
Para cada una:
Issue
Options
Impact
Recommendation
Decision required

K. Proposed Sprint Structure
Propón los checkpoints necesarios para ejecutar esta modificación completa.
Preferencia:
Baseline
→ Roles
→ Hierarchy
→ Data Scope
→ Administration UX
→ Security/Regression
→ Closure

pero ajusta la secuencia si el repositorio demuestra una mejor.
L. Effort Estimate
Entrega estimación realista por checkpoint.
Para cada uno incluye:
Checkpoint
Scope
Estimated agent/developer effort
Main uncertainty
Dependencies

Incluye:
- estimación mínima;
- estimación probable;
- estimación alta;
- total del sprint.
Separa, si es posible:
analysis
backend
data/migrations
frontend
tests
regression
closure/report

No infles estimaciones por tareas DevOps/Git administrativas.
Explica qué supuestos podrían aumentar o reducir el esfuerzo.
M. Recommendation to Programmer
Termina con una recomendación concreta sobre:
1. si conviene realizar este cambio antes de RTE07;
2. tamaño/riesgo real;
3. arquitectura recomendada;
4. secuencia sugerida.
STOP
Después de entregar el análisis y la estimación:
STOP.
No implementes nada.
Rodrigo/CER revisará la recomendación y emitirá la instrucción formal del sprint.