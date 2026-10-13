# CER Route — RTE08: Activity del usuario / Supervisor–Executor

**Instrucción de desarrollo V1.0**  
**Tipo:** checkpoint funcional único (RTE08)  
**Estado:** autorizado para implementación dentro del alcance indicado; pendiente de certificación CER  
**Módulo / dominio:** CER Route — WorkSessions, Trips, ActivityExecution y consultas de Activity  
**Superficie:** experiencia de ejecución **My Route** (Web/Mobile)

## 1. Context / Current State

CER Route dispone de **dos rutas Activity independientes en experiencia y autorización**, que no deben cruzarse:

| Ruta | Experiencia | Propósito |
| --- | --- | --- |
| **`/admin/route/activity`** | Administración — User Activity / Activity Explorer | Explorar la actividad de supervisores/usuarios dentro del alcance administrativo permitido, con selector de supervisor. |
| **`/route/activity`** | **Supervisor / Executor — pestaña inferior `Activity` de My Route** | Consultar **exclusivamente la propia actividad** del usuario autenticado, sin selector de usuarios. |

La ruta personal `/route/activity` **ya existe** en el shell de ejecución y actualmente muestra el placeholder `The Activity Explorer is not built yet... RTE08`. Debe sustituirse **ese contenido**, no crear otra URL, pestaña ni entrada de menú. La navegación inferior existente **My Route / Activity / Me** permanece intacta.

La vista administrativa es la **referencia funcional y de componentes** para filtros temporales, resúmenes, agrupación y detalle. Su implementación ya incorpora correcciones **H-2 (consolidación Today)** y **R-1 (reconciliación de totales con viajes visibles)**; RTE08 debe reutilizar las reglas vigentes y no revertirlas. El filtro móvil de supervisores **H-1 pertenece exclusivamente a la vista administrativa**.

**Antes de cambiar código:** inspeccionar el repositorio/branch realmente vigente, rutas, componentes, servicios, contratos, roles y estado de integración de T-1/T-2 y H-1. Los nombres de archivos o contratos mencionados aquí son referencias conocidas del diagnóstico previo; verificar antes de depender de ellos. Si hay otros cambios en progreso, aislar el trabajo y no sobrescribirlos.

## 2. Objective

Completar `/route/activity` como **Activity personal del Supervisor/Executor**, replicando el comportamiento relevante de `/admin/route/activity` para consultar historial propio por **Day / Week / Month / Year**, con los mismos criterios de métricas, viajes, actividades, estados de millaje, agrupación y detalles.

**Diferencia funcional esencial:** la identidad consultada es **siempre** el usuario autenticado, resuelta por el servidor y restringida al tenant correspondiente. No existe selección de supervisor ni acceso transversal. Mantener la experiencia UX existente de My Route, mobile-first.

## 3. Scope — Functional Requirements

### FR-01 — Ruta y navegación personal

1. Reemplazar el placeholder de **`/route/activity`** por una vista Activity funcional dentro del shell Supervisor/Executor existente.
2. Conservar encabezado, navegación inferior, indicador de pestaña activa, estilos, responsive y patrones visuales propios de My Route. Mostrar el nombre visible **`Activity`** conforme al menú aprobado; no renombrar la navegación a `My Activity` ni trasladarla al menú de administración.
3. Mantener acceso directo por URL, actualización de página, navegación entre pestañas y comportamiento correcto al retornar desde My Route/Me.
4. No mostrar encabezados, navegación administrativa ni controles de selección de otro usuario.

### FR-02 — Filtros temporales

1. Ofrecer los filtros ya existentes del Activity Explorer que sean aplicables a la actividad propia: **Day, Week, Month, Year** y el mecanismo de fecha/período de referencia aprobado.
2. Reutilizar, adaptar o compartir el componente/lógica actual de filtros en vez de crear reglas independientes. **Excluir completamente el selector de supervisor** de la vista personal.
3. Mantener la semántica de intervalos, selección de fecha, navegación entre períodos y estado vacío que utiliza el explorador existente; no agregar filtros no aprobados.
4. El usuario debe poder cambiar de período sin ver temporalmente resultados anteriores atribuidos al período recién seleccionado. Conservar coherencia entre filtros, resumen y detalle.

### FR-03 — Resumen y detalle del Activity Explorer

1. Presentar para el período elegido los resúmenes actualmente disponibles y relevantes en la vista administrativa (p. ej., millas, cantidad de actividades y demás indicadores existentes **sin inventar nuevos KPIs**).
2. Reutilizar la **agrupación temporal vigente** (días y vistas acordeón/tarjetas donde corresponda), el orden cronológico y los comportamientos existentes de expansión de detalle.
3. Mostrar los **viajes del usuario** y sus actividades reales, incluidos viajes sin `ActivityExecution` cuando contribuyen a métricas, conforme a **R-1**. No ocultar Home/return trips u otros viajes válidos sólo por carecer de una actividad asociada.
4. El contador **Activities** debe contar actividades reales y **no** el número de viajes/tarjetas. No inventar `In progress` para un viaje sin actividad.
5. Mantener diferenciados: millaje calculado, `pending_calculation`, estados terminales no calculables o fallidos, y cualquier indicador existente. **Nunca presentar millas pendientes como millas definitivas** ni cambiar fórmulas de negocio.
6. Conservar la presentación de actividades `IN_PROGRESS` conforme al contrato existente y las reglas vigentes de conciliación. Un registro sin resultado todavía no debe fingir un resultado final.
7. Manejar períodos sin datos, errores, espera de red y reintentos usando los patrones visuales aprobados. No mezclar datos de jornadas/usuarios por caché o respuestas asincrónicas tardías.

### FR-04 — Fecha, zona y formato horario

1. Respetar el contrato temporal **efectivamente aprobado e integrado de T-1/T-2**: timestamps como instantes absolutos, `WorkSession.session_date` asociada a la fecha local de inicio, y presentación en la zona de referencia de la jornada según su disponibilidad fiable.
2. Mostrar las horas visibles en el **formato AM/PM limpio** aprobado para CER Route, **sin sufijos UTC/EST/EDT repetidos en listados/tarjetas**; conservar fechas explícitas cuando cruces de medianoche generen ambigüedad.
3. Calcular duraciones con instantes reales, **no** restando textos de reloj ni usando la zona horaria del navegador del administrador como sustituto de la zona de la jornada.
4. No redefinir el día operativo, convertir históricos artificialmente, introducir reglas alternativas de timezone ni implementar T-1/T-2 dentro de RTE08. Si la rama aún no incluye T-1/T-2, implementar contra la base disponible sin duplicar la solución temporal y documentar la dependencia de integración/regresión.
5. Si un supervisor inició una jornada un día y la terminó al siguiente, los viajes/actividades permanecerán atribuidos según las reglas vigentes de `session_date`, sin partición/reasignación improvisada.

### FR-05 — Web/Mobile

1. La experiencia **móvil es prioritaria**. Ajustar la presentación existente a anchos estrechos (~360, 390 y 430 px), sin scroll horizontal, superposiciones, controles cortados ni interferencia con la barra inferior.
2. Preservar consistencia de datos en navegador de escritorio para un usuario de ejecución, pero **sin copiar el chrome administrativo**.
3. Reusar tarjetas, acordeones, filtros, formato horario y estados de carga del Explorer donde sean compatibles con el shell personal. Hacer adaptaciones visuales mínimas necesarias; **no se autoriza un rediseño**.
4. No introducir un flujo de edición de viajes o actividades, ni acciones de End Work/odómetro dentro de la vista histórica.

## 4. Business Rules

- **BR-01:** Activity personal contiene sólo WorkSessions/Trips/ActivityExecutions del **usuario autenticado** en su **tenant/company autorizado**.
- **BR-02:** Ningún filtro visible, parámetro de URL, header o cuerpo de request puede sustituir la identidad personal validada por el servidor.
- **BR-03:** Para el mismo usuario y período, las métricas y el detalle de `/route/activity` deben coincidir con los de `/admin/route/activity` cuando un administrador autorizado selecciona a ese mismo usuario, salvo diferencias expresas de presentación. Si existe una diferencia, documentar la causa; **no** modificar fórmulas en esta tarea.
- **BR-04:** La reconciliación **R-1** permanece intacta: trips sin actividad siguen en el detalle, mientras que el contador de actividades responde a `ActivityExecution` reales.
- **BR-05:** Respetar la agregación de múltiples WorkSessions de un mismo día, estados de actividad y estados del millaje existentes, sin cambiar sus definiciones.
- **BR-06:** No exponer ni construir directorios de otros supervisores en el cliente personal.
- **BR-07:** No crear ni cambiar jornadas, viajes o actividades al consultar la pantalla. Es una vista **read-only**.
- **BR-08:** Navegar a la vista personal no debe conferir privilegios administrativos ni ampliar el alcance del Activity Explorer.

## 5. Roles, Permissions & Scope — Obligatorio

**Principio:** ocultar el selector en frontend **no constituye autorización**. El aislamiento debe ser **server-side**.

1. Verificar cómo el shell Supervisor/Executor protege actualmente las rutas y qué capacidad permite al usuario autenticado consultar sus propios datos.
2. **No exigir `route.activity.read` como prerrequisito para consultar la actividad propia** si ese permiso actualmente da acceso al Explorer administrativo. Mantener íntegra la autorización de `/admin/route/activity`, que sigue bajo `route.activity.read` y validación de alcance.
3. Implementar/reutilizar un **contrato self-scoped** cuyo sujeto se derive de la sesión autenticada y del tenant resuelto por el servidor. El diseño técnico exacto (endpoint personal, capa de servicio compartida u otra variante equivalente) lo elige el desarrollador dentro de la arquitectura existente; debe preservar un límite de autorización inequívoco.
4. Reutilizar las consultas y reglas de negocio del Activity Explorer, evitando copiar lógica de agregación, duplicar SQL sin necesidad o acceder directamente a dominios de forma que cree acoplamiento innecesario.
5. Si **no existe** una capacidad personal apropiada y la alternativa segura exige crear/modificar RBAC, documentar propuesta, alcance y compatibilidad y **solicitar aprobación al PO antes de alterar catálogos, seeds o permisos**. No elevar permisos de Supervisor/Executor otorgando `route.activity.read` ni debilitar el guard administrativo para desbloquear esta vista.
6. Una petición manipulada con `supervisor_user_id`, `user_id`, `company_id`, `tenant_id` o identificador ajeno no debe devolver datos de otro usuario. Rechazar o ignorar el parámetro sin exponer datos; definir y probar el tratamiento real elegido. Incluso un administrador usando **`/route/activity`** debe recibir **sólo su propia actividad**.
7. Probar acceso no autenticado, acceso personal autorizado, solicitudes de otros usuarios del mismo tenant, cruce de tenants y denegación administrativa para el ejecutor no autorizado.
8. Evitar filtrar PII ajena mediante payload, catálogos, trazas o errores.

## 6. APIs / Data / Existing Components to Reuse

**Verificar en repositorio antes de editar:**

- Vista administrativa: `pages/RouteActivityExplorerPage/ui/RouteActivityExplorerPage.tsx`.
- Filtros: `features/RouteActivityExplorer/ui/ExplorerFilterBar.tsx` y componentes actuales de tarjetas/acordeones.
- API administrativa: `GET /api/activity-explorer` (`range`, `date`, `supervisor_user_id`), con su autorización existente `route.activity.read`.
- Dominio y DAO: `app/routers_api/activityexplorer/`, `agregados_por_dia`, `paradas_del_dia`, contratos compartidos para viajes sin actividad (`has_activity`, campos de AE opcionales).
- Shell y ruta personal `/route/activity` y su placeholder actual; servicios/API/types/Zod reutilizables.

**Impacto esperado:** consulta y pantalla personal; lógica compartida donde corresponda. **Sin migraciones**, sin nuevos catálogos, sin actualización de datos históricos, sin nuevas métricas y sin cambios en kilometraje.

Si se necesita un endpoint personal, debe exponer únicamente datos del usuario autenticado y reutilizar las mismas estructuras de resumen y detalle; no aceptar un selector arbitrario de supervisor. Evitar romper contratos públicos existentes o la vista administrativa. Las modificaciones compartidas son aceptables sólo si son compatibles y vienen acompañadas de regresiones administrativas.

## 7. Edge Cases

- Usuario autorizado sin ninguna WorkSession: pantalla vacía correcta, no error ni información de terceros.
- Usuario con jornadas en múltiples días, con varias WorkSessions un mismo día o una jornada que cruza medianoche: agrupación y totales correctos según fecha operativa.
- Usuario con viajes pero sin `ActivityExecution`, incluido regreso a casa: detalle completo, contador correcto.
- Actividades en progreso, viajes incompletos y millas pendientes/fallidas: estados reales, sin inventar resultados.
- Usuario con perfil administrativo y actividad propia: vista `/route/activity` **sólo self**, no menú de supervisores.
- Usuario sin `route.activity.read` que sí tiene acceso autorizado a su experiencia de ejecución: consulta personal accesible, pero Explorer admin denegado.
- Cambio rápido entre Day/Week/Month/Year o navegación entre pestañas durante una solicitud: sin mezclar respuestas ni datos de filtros anteriores.
- Datos legados con offset pero sin zona IANA: seguir regla temporal integrada; no asumir zonas ni alterar históricos.
- Refresco, acceso por URL directa, sesión expirada y pérdida de conexión: estados recuperables sin fuga de información ni cambios en la WorkSession.

## 8. Acceptance Criteria

| ID | Verificación exigida |
| --- | --- |
| **AC01** | `/route/activity` ya no presenta el placeholder de RTE08; funciona dentro del shell Supervisor/Executor con pestaña inferior Activity activa. |
| **AC02** | Day/Week/Month/Year y fecha de referencia filtran resúmenes y detalle de forma coherente. |
| **AC03** | Resúmenes, días agrupados, viajes, actividades y resultados son funcionalmente equivalentes al Explorer administrativo para **ese mismo usuario y período**. |
| **AC04** | No existe selector de supervisor ni listado de otros usuarios, en móvil o escritorio. |
| **AC05** | El servidor fija el sujeto al usuario autenticado y aplica tenant isolation; manipular parámetros no permite consultar registros ajenos. |
| **AC06** | Un Supervisor/Executor sin privilegio administrativo puede ver sus datos propios y sigue sin acceder al Explorer de administración. Si falta una capacidad personal existente, se eleva la decisión RBAC antes de modificar permisos. |
| **AC07** | Todos los viajes relevantes aparecen, incluidos los que carecen de actividad; el contador de actividades **no** cuenta esos viajes como actividades. |
| **AC08** | Millaje calculado/pendiente/no calculable/fallido, estados de actividades y múltiples jornadas conservan su semántica vigente; no se duplican filas ni millas. |
| **AC09** | Fechas y horas siguen las reglas integradas T-1/T-2 y formato AM/PM aprobado, sin sufijos de zona repetidos. |
| **AC10** | My Route, Me, barra inferior, navegación y experiencia mobile-first permanecen intactos y son utilizables sin overflow. |
| **AC11** | `/admin/route/activity`, el filtro móvil H-1 y los permisos administrativos permanecen funcionalmente sin cambios. |
| **AC12** | No hay migraciones, cambios de cálculos, nuevas acciones operativas ni mutaciones provocadas por consultas de Activity. |

## 9. Tests Required / Validation

### Integración y seguridad

1. Consultas personales devuelven sólo datos del usuario autenticado en tenant correcto, incluso si otro usuario del mismo tenant tiene viajes ese día.
2. Tampering con `supervisor_user_id`, `user_id`, `company_id` y tenant diferente: sin acceso a datos ajenos, independientemente de frontend.
3. Ejecutor habilitado para uso personal **sin** `route.activity.read`: acceso personal correcto y acceso admin bloqueado; usuario no autenticado rechazado.
4. Administrador autorizado con actividad propia: su ruta personal es self, su ruta admin sigue usando alcance administrativo.
5. Paridad numérica con respuesta administrativa autorizada para el mismo usuario/período; incluir varios días, varias WorkSessions y viaje sin actividad.
6. Estados `IN_PROGRESS`, millaje pendiente/fallido, resultados vacíos y cambio de zona/fecha operativo según regla T-1/T-2 integrada.

### E2E Web/Mobile

1. **Móvil 365 px** (y verificar ~360/390/430): abrir pestaña Activity desde My Route, consultar períodos, expandir días/tarjetas y volver a My Route/Me.
2. Navegación directa/refresco en `/route/activity`; sin placeholder, sin admin chrome, sin filtros de supervisor.
3. Dos usuarios diferentes con datos conocidos: iniciar sesión con cada uno y comprobar que sólo ve lo propio; no filtrar desde el cliente después de recibir respuestas multisuarios.
4. Comparar visualmente/numericamente Activity personal con User Activity administrativo filtrado al mismo usuario en un período conocido.
5. Verificar adaptación a móvil sin scroll horizontal ni solapamiento con barra inferior, así como escritorio con shell de ejecución.
6. Solicitud lenta/error, con cambio de filtros: nunca mostrar datos ajenos o de otro período con etiqueta incorrecta.

### Regresiones

- Ejecutar pruebas relevantes del Activity Explorer administrativo, H-1, R-1, H-2 y permisos. Probar My Route/Me y el shell Supervisor/Executor.
- Si T-1/T-2 está integrado, ejecutar su regresión temporal; si no, registrar dependencia para la validación integrada, **sin implementar temporalidad paralela**.
- Distinguir pruebas ejecutadas, no ejecutadas, fallos preexistentes y defectos nuevos. El mismatch antiguo de `test_provisioning_alignment` (14 vs 12 capacidades) no autoriza modificar roles o fixtures fuera de este alcance.
- Evidencia de navegador real o entorno equivalente, con capturas **móvil** y **desktop** y comparación de resultados con admin. No declarar QA certificado únicamente porque compila.

## 10. Out of Scope / Do Not Change

- No alterar URL, nombre de menú, pantalla, permisos ni experiencia de **`/admin/route/activity`**.
- No implementar el filtro H-1 aquí: H-1 corresponde a la vista administrativa móvil.
- No cambiar Today/Live ni H-3 Current/Last Activity.
- No implementar P-2, End Work, Keep working, odómetro, recuperación de jornada ni sincronización offline.
- No rehacer T-1/T-2 ni introducir nueva lógica de zona horaria; sólo consumir su contrato vigente y aplicar formato aprobado.
- No mover, re-fechar, corregir, eliminar ni crear registros históricos; no tocar fórmulas de mileage, actividades ni WorkSessions.
- No agregar navegación, menús, selectores de usuario, nuevos dashboards, reportes, exportaciones, catálogos o funcionalidades administrativas.
- No rediseñar el mockup/UX aprobado de My Route. **Replicar capacidad funcional, no copiar literalmente el chrome de administración.**
- No fusionar ni desplegar sin autorización del Product Owner.

## 11. Deliverables / Checkpoint Closure

Entregar **un solo** informe de implementación `CER_ROUTE_RTE08_PERSONAL_ACTIVITY_IMPLEMENTATION_REPORT.md` con:

1. Branch, SHA base y **AS-BUILT verificado**: ruta placeholder, componentes disponibles, endpoint y permiso existente.
2. **Expected vs Implemented** para AC01–AC12 (Completed / Partial / Blocked / Pending Validation, con evidencia).
3. Componentes y servicios reutilizados versus cambios reales (frontend/backend), APIs, contratos, RBAC, modelo de datos y migraciones.
4. Explicación explícita del aislamiento personal y las pruebas de seguridad **server-side**; indicar si hubo decisión RBAC que requirió autorización.
5. Capturas móvil y escritorio del Activity personal, más comparación con Activity administrativo para un usuario/período conocido.
6. Comandos y resultados de integración, E2E, regresiones (pass/fail/skip/not-run), fallos conocidos y cualquier dependencia con T-1/T-2/H-1.
7. MR, commit SHA, estado de merge/despliegue y riesgos restantes.

**Definition of Done:** un usuario Supervisor/Executor puede consultar y filtrar **toda su propia actividad** en `/route/activity` desde móvil sin placeholder ni controles administrativos; los resultados son reconciliables con el Explorer administrativo para ese usuario, el servidor impide consultar datos ajenos y My Route/Today/Admin conservan sus comportamientos. Si faltan pruebas de seguridad o paridad, clasificar **Partial / Pending Validation**, no Completed.

**Gobierno:** RTE08 es **un checkpoint funcional completo**. Sólo escalar decisiones que cambien permisos o reglas de negocio; no fragmentar en nuevos checkpoints por tareas técnicas.
