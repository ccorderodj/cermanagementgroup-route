# CER Route — Jerarquía organizacional, roles, permisos y alcance de datos

**Instrucción de desarrollo V1.0**  
**Fecha:** 13 de octubre de 2026  
**Destino:** Desarrollador y agente técnico de CER Route  
**Tipo:** Desarrollo funcional / seguridad y gobierno de accesos  
**Estado:** Alcance funcional autorizado; decisiones técnicas sensibles sujetas a la puerta de control indicada abajo  
**Regla de producto vigente:** **OSM y Supervisor tienen exactamente el mismo nivel de accesos en esta etapa.**

---

## 1. Context

CER Route dispone de una experiencia administrativa y otra de ejecución (*My Route / Activity / Me*). El siguiente desarrollo busca que los permisos y la visibilidad de la información correspondan a la estructura operativa de CER Management Group, sin crear experiencias independientes para cada cargo.

Se han acordado los cargos **Superadmin, CEO, COO, Regional Manager (RM), On-Site Manager (OSM) y Supervisor**. El cargo organizacional **no debe confundirse** con un permiso técnico: un usuario podrá realizar una operación únicamente si posee la capacidad correspondiente **y** actúa sobre datos autorizados por su alcance jerárquico y tenant.

La decisión más reciente del Product Owner modifica la representación anterior: **OSM y Supervisor son pares, no niveles de acceso diferentes**. OSM no es superior de Supervisor por defecto, no recibe permisos de administración ni ve la actividad de otros usuarios por el solo hecho de tener ese cargo.

## 2. Current State — verificación obligatoria

Antes de implementar, verificar en la rama vigente el AS-BUILT y documentar archivos/contratos exactos de:

- Roles, capacidades, membresías de compañía y permisos actuales, incluidos `route_admin` y `route.worksession.execute`.
- Modelo de `User`, `SupervisorProfile`, relaciones de subordinación (si las hay), asignación de cargos y administración de usuarios.
- Middleware y verificaciones server-side de identidad, compañía y permisos.
- Consultas de `Today / Live`, `Activity` administrativo, `Reports` y selectores de supervisor; identificar cualquier consulta que actualmente tenga *company-wide scope*.
- Flujos de ejecución personal (`/route/*`), incluida `/route/activity`, y su restricción actual al usuario autenticado.
- Paneles administrativos ya existentes para Users / Roles / configuración y utilidades de auditoría.
- Pruebas de permisos y catálogo de capacidades. En diagnósticos previos figuraba una discrepancia **14 capacidades reales vs. 12 esperadas** para `route_admin` en `test_provisioning_alignment`; verificar el estado actual y **no corregirla cambiando permisos, fixtures o tests sin aprobación**.

**No asumir que el preflight de septiembre está implementado.** El resultado del inventario será evidencia primaria; si contradice este documento, informar el conflicto antes de alterar contratos críticos.

## 3. Objective

Implementar una jerarquía organizacional operativa y un mecanismo único de autorización que permitan:

1. Asignar el cargo y el superior de un usuario dentro de una misma compañía.
2. Conservar niveles intermedios opcionales sin romper la cadena de supervisión.
3. Limitar los datos visibles en las pantallas administrativas al conjunto de usuarios subordinados autorizado, sin depender de filtros del frontend.
4. Delegar exclusivamente la administración de usuarios, relaciones y asignaciones permitidas para cada nivel.
5. Mantener para **OSM y Supervisor** los mismos permisos de ejecución y consulta personal, sin privilegios sobre otros usuarios.
6. Conservar las interfaces actuales; no duplicar módulos ni crear dashboards por cargo.

## 4. Scope / Out of Scope

### Dentro del alcance

- Modelo de cargo/posición organizacional y relación de superior activo, reutilizando componentes existentes cuando sea viable.
- Políticas server-side de **RBAC + data scope** y administración delegada.
- Restricción efectiva en listados, filtros, resúmenes, detalles y consultas administrativas relevantes de CER Route.
- Ajustes mínimos en administración de usuarios/roles/relaciones usando pantallas existentes.
- Auditoría de cambios sensibles, migraciones aditivas justificadas y pruebas de seguridad/regresión.

### Fuera del alcance

- Cambiar el shell **My Route / Activity / Me**, el flujo de jornada, Trips, Activities, odómetros, millaje o geolocalización.
- Rediseñar Today / Activity / Reports o crear páginas por CEO, COO, RM u OSM.
- Modificar lógica de T-1/T-2, P-2, H-1, H-3 o RTE08.
- Replicar automáticamente todos los permisos de CER ERP o alterar la seguridad de otros módulos.
- Dar permisos de administración al OSM, al Supervisor o a otro cargo sin autorización.
- Crear un editor libre del catálogo global de capacidades o conceder privilegios mediante *role rank* sin validación server-side.
- Migrar o reasignar masivamente subordinados existentes por inferencia.

## 5. Hierarchy — reglas confirmadas

**Superadmin** es una facultad administrativa de CER Route (por ejemplo, `route_admin` si así lo confirma el inventario), **no** un supervisor operativo que deba ocupar necesariamente un nodo en la cadena de reportes. Nunca confundirlo con el superusuario de plataforma ni interpretarlo como autorización inter-tenant.

Jerarquía funcional de responsabilidades:

```text
CER Route Superadmin [administración del producto dentro del tenant autorizado]

CEO
 └── COO                 (nivel opcional)
      └── Regional Manager (nivel opcional)
           ├── OSM        (nivel de acceso ejecutor)
           └── Supervisor (mismo nivel de acceso ejecutor)
```

**Los niveles intermedios son opcionales**: si no existe COO o RM en una rama, un usuario puede reportar al superior existente de nivel más alto, siempre que no haya dependencia lateral ni hacia abajo. No debe exigirse crear cargos ficticios para completar la cadena.

Reglas de integridad:

- Un usuario tiene **como máximo una posición/relación de superior activa por compañía**; esto no impone artificialmente un único rol RBAC si el sistema actual admite varios.
- Cada subordinado tiene como máximo **un superior activo** en la estructura correspondiente.
- El superior debe tener un nivel organizacional **estrictamente superior** al del subordinado; no existen vínculos laterales OSM→Supervisor ni Supervisor→OSM.
- No se admiten ciclos, autoasignaciones ni referencias entre compañías.
- La relación entre superior y subordinado **no otorga por sí sola** capacidades funcionales adicionales; habilita *data scope* solamente para operaciones autorizadas.
- Los cambios de cargo o superior deben validarse de forma transaccional y auditada; no pueden dejar relaciones activas inconsistentes.
- El árbol organizacional debe admitir múltiples RM y múltiples ejecutores, cada uno en su respectiva rama.

## 6. Functional access policy

La siguiente matriz es el **objetivo de negocio**, sujeto a verificar las capacidades preexistentes. Una celda de administración **nunca** habilita cambios de privilegios más altos o fuera del propio alcance.

| Cargo | Visibilidad de información administrativa | Administración delegada | Experiencia Execute / Activity personal |
|---|---|---|---|
| **CER Route Superadmin** | Toda la compañía/tenant para el que esté autorizado | Usuarios, roles, relaciones y configuración de CER Route dentro del tenant; respetar controles superiores de plataforma | Sí, **solo actividad propia** en `/route/activity` |
| **CEO** | Su ámbito organizacional/subordinados dentro de su compañía | Personal de niveles inferiores, relaciones y catálogos de CER Route conforme a capacidades concedidas | Sí, propia |
| **COO** | Su árbol de subordinados (RM y ejecutores) | Personal inferior, relaciones y asignaciones delegadas de roles/permisos aprobados; nunca puede conceder facultades de CEO, Superadmin o superiores a las suyas | Sí, propia |
| **Regional Manager** | Su árbol de ejecutores subordinados (OSM/Supervisor) | Gestión de personal y relaciones de ejecutores subordinados conforme al catálogo autorizado; **no** administrar capacidades globales | Sí, propia |
| **OSM** | Su propia información de ejecución | **No** administra roles, usuarios ni relaciones | Sí, propia |
| **Supervisor** | Su propia información de ejecución | **No** administra roles, usuarios ni relaciones | Sí, propia |

**Decisión explícita e innegociable:** OSM y Supervisor deben producir el **mismo conjunto efectivo de capacidades, menús autorizados y política de alcance de datos**. Conservar el título/cargo diferenciable para organización y reportes, pero no crear una segunda clase privilegiada de ejecutor.

**No crear capacidades de autorización nuevas a partir de esta matriz sin inventario y justificación.** Si la administración delegada necesita capacidades ausentes o una nueva estrategia de asignación de privilegios, presentar un *decision gate* con propuesta mínima al Product Owner; no adoptar silenciosamente permisos amplios por comodidad.

## 7. Use cases y flujos principales

### UC-01 — Administrador autorizado configura una relación

1. Abre la administración existente de usuarios/organización.
2. Selecciona usuario y cargo organizacional (entre cargos autorizados).
3. Selecciona superior de una lista restringida a niveles válidos, **misma compañía y ámbito delegable**.
4. El servidor vuelve a validar permisos, cargo, tenant, superior único, ausencia de ciclos y alcance de la operación.
5. Confirma el cambio, conserva audit trail y la nueva estructura rige las siguientes consultas autorizadas.

Si no hay un superior intermedio, permitir seleccionar un superior más alto válido. Si existe un usuario cuyo cargo no permite superior en la rama, respetar la regla de raíz definida por el modelo.

### UC-02 — RM revisa Today / Activity / Reports

El RM visualiza **solo su propio conjunto autorizado de subordinados** en las vistas administrativas para las que tenga capacidad. Los resúmenes, cifras, detalles, opciones de filtro, descargas y APIs deben derivarse del mismo alcance.

Intentar solicitar por API el `user_id` de otro RM, otro equipo o compañía debe denegarse, aunque se cambien manualmente parámetros o se conozcan identificadores válidos.

### UC-03 — CEO/COO administran subordinados

El usuario con capacidad delegada gestiona exclusivamente personas/cargos/relaciones de nivel inferior dentro de su alcance, sin autoconcederse permisos ni ascender terceros a su mismo nivel o a uno superior.

### UC-04 — OSM y Supervisor ejecutan

Ambos acceden a las mismas capacidades operativas autorizadas de My Route y a la pestaña Activity propia. Ninguno obtiene por cargo la vista administrativa de otro supervisor ni el selector global de supervisores.

### UC-05 — Administrador que también realiza rutas

Al entrar a `/route/activity`, ve únicamente **su propia** actividad, aunque también pueda consultar subordinados desde `/admin/route/activity`. No compartir parámetros de scope administrativo con la experiencia personal.

## 8. Data scope and API / Services

Implementar/reutilizar una **única política server-side** para determinar el conjunto de usuarios visibles por un actor, compañía y acción:

- **Self scope**: el usuario autenticado, para acciones y reportes personales.
- **Descendant scope**: subordinados válidos en la cadena activa, para usuarios con capacidades de supervisión.
- **Tenant authorized scope**: administración integral del tenant para `route_admin` autorizado, sin alcanzar otras compañías.

El alcance se calcula **en servidor**, verificando rol/capacidad y relaciones; no se basa en campos enviados por el cliente ni en ocultar controles visuales.

Aplicar la política en las superficies administrativas existentes según disponibilidad real:

- `/admin/route/today` y `GET /api/live/today`.
- `/admin/route/activity` y APIs de Activity Explorer; listado de supervisores, filtros, resúmenes y detalle.
- Reports: consultas, KPIs, desglose, descargas/exportación y filtrado, si están implementados.
- APIs de Users / Roles / Organization utilizadas para delegación.

Mantener la posibilidad de que un usuario con capacidades administrativas ejecute su propia jornada. Para las rutas `/route/*` nunca delegar *self scope* al filtro administrativo.

En listados/aggregates, filtrar **antes de agregar**, para evitar filtraciones mediante conteos, totales, kilometraje, búsqueda, paginación o índices. En consultas específicas de usuario fuera de alcance, utilizar la convención existente para no revelar identidades (por ejemplo, 404) sin sustituir la autenticación/autoridad requerida.

No crear dependencias entre dominios de CER ERP/CER Time; el alcance pertenece al dominio de organización/acceso de CER Route y debe exponerse mediante interfaces reutilizables.

## 9. Data model impact

Priorizar los modelos y tablas existentes. Solo si no soportan la estructura aprobada, agregar una representación mínima y auditable de:

- Compañía/tenant de la relación.
- Usuario subordinado y usuario superior.
- Cargo/posición vigente cuando corresponda.
- Vigencia/estado de la relación y metadatos de auditoría.

La solución debe garantizar superior activo único, integridad de referencias, validación de cargo relativo y protección ante escrituras concurrentes. No imponer nombres de tablas/columnas si existe un modelo válido reutilizable.

**Migraciones:** deben ser aditivas, reversibles y probadas; no cambiar ni rellenar automáticamente la jerarquía de usuarios existentes sin instrucciones expresas del PO. Usuarios aún sin asignación deben permanecer operativos en su experiencia personal, sin recibir acceso administrativo más amplio por ausencia de superior.

**Historical access decision boundary:** al transferir un supervisor de RM-A a RM-B, la visibilidad de registros históricos puede seguir la jerarquía vigente o la jerarquía histórica. **No existe una decisión aprobada explícita sobre esto.** Antes de implementar exposición histórica entre superiores, presentar al PO las dos opciones, sus riesgos de privacidad y la recomendación; en ausencia de resolución, mantener un enfoque restrictivo que evite exposición nueva no autorizada. Esto no justifica inventar históricos ni bloquear el desarrollo de los invariantes y el modelo base.

## 10. Web / Mobile

- Reutilizar administración actual de usuarios/roles; sumar únicamente controles mínimos de cargo y superior donde correspondan.
- No crear paneles diferentes por CEO, COO, RM, OSM y Supervisor.
- La navegación existente muestra únicamente opciones para las que el usuario tenga permiso efectivo, **sin tratar el menú como barrera de seguridad**.
- Conservar `/admin/route/activity` exclusivamente para experiencia administrativa y `/route/activity` para Activity propia del Supervisor/Executor.
- Conservar la navegación inferior de My Route; OSM y Supervisor ven la misma experiencia de ejecución.
- Probar escritorio y móvil, con y sin niveles intermedios, y sin regresión de los filtros existentes.

## 11. Security / Audit

- Validar compañía, permisos de acción, jerarquía y alcance **en cada operación del servidor**.
- Rechazar escalamiento propio, ediciones de superiores de igual/mayor jerarquía, asignaciones cruzadas de tenant, ciclos y relaciones laterales.
- Evitar que el CRUD de usuarios, un endpoint de reportes o una exportación eludan el filtro jerárquico.
- Registrar quién cambió cargo, superior, asignaciones delegadas y permisos; cuándo, entidad afectada y valores anterior/nuevo. Reutilizar `audit_event` o el mecanismo vigente.
- En cambios de superior, revocar el acceso anterior en las próximas consultas y evitar filtros o cachés que reutilicen scope obsoleto.
- Tratar los IDs como referencias no confiables y comprobar autorización en backend.
- No alterar el conjunto de capacidades de `route_admin` solo para hacer pasar una prueba desactualizada; requiere decisión explícita de catálogo de seguridad.

## 12. Acceptance Criteria

1. **AC01**: Superadmin CER Route puede administrar el ámbito autorizado sin acceso cross-tenant ni privilegios de plataforma implícitos.
2. **AC02**: CEO, COO y RM consultan exclusivamente los usuarios y datos de su scope jerárquico y para capacidades concedidas.
3. **AC03**: OSM y Supervisor reciben **idénticas capacidades de aplicación**, UX autorizada y *self-only data scope*.
4. **AC04**: OSM no puede gestionar Supervisores, relaciones ni permisos por el solo título de OSM.
5. **AC05**: Los niveles intermedios son opcionales y funcionan los vínculos verticales válidos sin crear posiciones ficticias.
6. **AC06**: Un subordinado no tiene dos superiores activos; las relaciones laterales, circulares, propias o entre compañías se rechazan.
7. **AC07**: Administradores delegados no pueden ascender roles/cargos a su nivel o superior ni otorgar permisos fuera de su capacidad delegable.
8. **AC08**: Today, Activity y Reports disponibles usan el mismo alcance en filtros, totales, detalle, búsqueda, paginación y exportación.
9. **AC09**: Un administrador que ejecuta jornadas solo ve su propia Activity en `/route/activity`.
10. **AC10**: Cambiar un superior actualiza/revoca acceso de forma segura sin contaminación de caché y con auditoría.
11. **AC11**: Usuarios existentes sin relación jerárquica mantienen ejecución personal sin obtener acceso administrativo nuevo.
12. **AC12**: Se conservan rutas, diseño y lógica operativa preexistentes; no aparecen privilegios nuevos por migración o seed.
13. **AC13**: Auditoría identifica autor, compañía, objeto, instante y cambios relevantes.
14. **AC14**: Las pruebas específicas, de seguridad y regresión correspondientes pasan o se reportan con evidencia y clasificación clara.

## 13. Tests Required

**Integración / seguridad:**

- Al menos dos tenants, dos RM distintos y ejecutores bajo cada RM.
- CEO→COO→RM→OSM/Supervisor; CEO→RM→Supervisor; COO→Supervisor; RM→OSM, sin capas ficticias.
- OSM y Supervisor con la **misma** matriz de permisos; accesos propios; rechazo de CRUD ajeno y consulta de otro usuario.
- Usuarios con superior inválido, ciclo, superior duplicado o concurrencia; cambios auditados.
- Intentos de permisos elevados (RM→COO, OSM→RM, autoasignación de `route_admin`, etc.).
- Restricción de `Today`, Activity Explorer y Reports a nivel de datos, incluidos agregados/contadores, filtros, exportaciones y endpoints directos.
- Admin con trabajo personal y con vista administrativa, con scopes diferenciados.
- Cambio y desasignación de superior, usuario inactivo, miembro de otra compañía, usuario sin superior.
- Evidencia de aislamiento cross-tenant con IDs válidos conocidos.
- Regresión de las capacidades existentes; explicar `test_provisioning_alignment` si continúa discrepancia 14/12 sin manipular fixture.

**E2E Web/Mobile:**

- Iniciar sesión como CEO, COO, RM, OSM y Supervisor con datos de prueba diferenciados.
- Confirmar visibilidad real de menús, filtros, personal y métricas según alcance.
- Probar dos ramas RM para asegurar que ningún usuario ve la rama ajena.
- Confirmar igualdad efectiva de la experiencia de OSM y Supervisor.
- Verificar My Route y Activity personal sin regresiones.

Las pruebas deben ejecutarse en entorno aislado; no reasignar usuarios reales solo para obtener capturas.

## 14. Do Not Change

- Separación `/admin/route/activity` frente a `/route/activity`.
- Correcciones H-2/R-1, T-1/T-2 y otros checkpoints sin necesidad directa.
- Definiciones de viajes, estados de actividad, cálculo de millaje, odómetros, End Work o offline.
- Interfaces y navegación aprobadas fuera de ajustes mínimos a la administración de jerarquía.
- Permisos de plataforma, Core transversal o tenant de otros módulos.
- Permisos de OSM por encima de Supervisor.

## 15. Deliverables

Entregar un archivo MD de implementación con evidencia, como mínimo:

1. **AS-BUILT / CONFIRMED**: modelos, roles, capacidades, endpoints y pantallas existentes analizados, con referencias concretas.
2. **Expected vs Implemented** por AC, con rutas/servicios/modelos modificados.
3. Diagrama o tabla final de cargos, permisos y alcance de datos, incluidos OSM=Supervisor y delegación efectiva.
4. Migraciones y plan de despliegue/provisioning, si aplican, con integridad de datos y reversión.
5. Auditoría y controles de seguridad implementados; cobertura por rutas administrativas y personales.
6. Evidencia de pruebas de integración, seguridad y navegador Web/Mobile, con comandos y resultados reales.
7. Riesgos, límites y **decisiones pendientes** — particularmente visibilidad histórica tras reasignaciones y posibles capacidades delegables ausentes.
8. Branch, commit SHA, MR y estado de integración/despliegue.

Clasificar cada apartado como **COMPLETED / PARTIAL / BLOCKED / PENDING VALIDATION**, sin declarar completado el desarrollo por compilar o por una UI aparentemente correcta.

## 16. Execution / Checkpoints

Este es **un solo frente funcional: Jerarquía + RBAC + Data Scope**, no una sucesión artificial de tickets.

- **Control A — Preflight breve y diseño de contratos:** verificar AS-BUILT, contratos reutilizables y cambios estrictamente necesarios. Elevar únicamente decisiones de producto/materiales de seguridad no cubiertas aquí, sin abrir subproyectos.
- **Control B — Desarrollo integral:** persistencia de jerarquía, política de alcance reutilizable, administración delegada y aplicación consistente en las superficies existentes.
- **Control C — Certificación:** evidencias y pruebas positivas/negativas por cargo, tenant, ruta y dato; no fusionar ni desplegar sin la autorización CER correspondiente.

Estos controles son **fases de verificación de una misma entrega**, no checkpoints adicionales del roadmap. Entregar una sola instrucción operativa y un informe final consolidado.

---

**Decisión vigente del Product Owner:** **OSM = Supervisor en accesos y permisos para la etapa actual.** Ni el organigrama ni un nombre de cargo habilitan una excepción.
