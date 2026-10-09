# CER Route — T-1/T-2: Timezone & Business Day Consistency

**Tipo:** instrucción de desarrollo / corrección funcional y de contratos temporales  
**Prioridad:** alta — prerrequisito de P-2 (recuperación de jornadas olvidadas)  
**Checkpoint:** **T-1/T-2, único entregable funcional**  
**Estado:** listo para análisis técnico de implementación; **requiere decisión explícita del Product Owner antes de cualquier cambio de esquema o política de asignación de zona**  
**Ámbito:** CER Route — WorkSessions, Trips, ActivityExecution, Today/Live, User Activity y visualización de horarios

## 1. Context / Current State

Los diagnósticos previos identificaron:

- PostgreSQL utiliza `timestamp with time zone` para los instantes examinados y `WorkSession.session_date` es `date`. **No existe evidencia que justifique convertir timestamps ni modificar datos históricos.**
- `WorkSession.start_utc_offset_minutes` conserva el offset reportado al inicio de una jornada, **no una zona horaria IANA** del supervisor.
- En la auditoría se informó que no existe una zona IANA persistida en `SupervisorProfile`, `Users` o `Company`; verificar el estado actual del repositorio antes de actuar.
- El cálculo actual de `business_day()` utiliza el offset de la última jornada iniciada **en toda la compañía**; eso puede determinar el «hoy» de otro supervisor usando un huso ajeno. Sin jornadas con offset, el fallback UTC tampoco equivale a la fecha local de los supervisores.
- En Today/Live, el día operativo y las horas visualizadas utilizan referencias diferentes: el backend determina la fecha con el offset anterior y el frontend usa `toLocaleTimeString()` en la zona del navegador del administrador.
- Today H-2 y User Activity R-1 ya consolidan millas y actividades conforme a `WorkSession.session_date`. No se debe deshacer esa corrección.
- El dominio soporta jornadas legítimas que atraviesan medianoche; su `session_date` corresponde a la **fecha local en que inició la jornada** y no debe cambiar al cruzar de día.
- Los eventos sincronizados offline conservan el instante de ocurrencia registrado al encolarse; no deben fecharse de nuevo al sincronizar.

**Decisiones de producto confirmadas:**

1. La referencia operativa de cada supervisor es **su día y su hora local**, no la zona del servidor ni la del administrador que consulta.
2. Una WorkSession nocturna sigue asociada al **día local de inicio**, aun si algunos eventos ocurren después de medianoche.
3. Los instantes deben mantenerse inequívocos y comparables; el almacenamiento existente no se sustituye por horas locales sin zona.
4. Se preservan las interfaces, menús, accesos y navegación actuales.
5. **T-1/T-2 se realiza antes de P-2**. No implementar aquí cierres retrospectivos ni recuperación de jornadas olvidadas.

## 2. Objective

Establecer un contrato temporal coherente para CER Route, que permita:

- Interpretar correctamente la **fecha local vigente de cada supervisor**.
- Mantener la **fecha operativa de una WorkSession** y los eventos de esa jornada sin atribuirlos a la fecha de otra persona.
- Presentar horarios correctos de Start Work, End Work, Depart, Arrived, Activity Start/End y demás eventos, **independientemente de la zona del navegador que consulta**.
- Conservar la misma semántica entre Today/Live y User Activity, con los filtros de fecha/periodo existentes.
- Soportar cambios de horario de verano (DST), zonas distintas y sincronización offline, sin modificar la evidencia histórica.

**Resultado exigible:** el administrador puede determinar cuándo trabajó realmente cada supervisor según su referencia horaria operativa, sin confundir el instante almacenado, la fecha de jornada y la fecha/hora de presentación.

## 3. Reglas temporales funcionales

**TR-01 — Instantes.** `started_at`, `ended_at`, salidas, llegadas, eventos de actividad y marcas de sincronización representan instantes absolutos. Mantener tipos y semántica existentes (UTC o timestamps aware equivalentes). No convertirlos a valores naive ni depender de la zona de sesión PostgreSQL o del proceso servidor.

**TR-02 — Zona operativa.** La zona que gobierna el calendario de un supervisor debe ser identificable de forma **estable e inequívoca**, preferentemente mediante un identificador IANA (`America/New_York`, `America/Chicago`, etc.). Un offset fijo (`-04:00`) **no determina** por sí mismo una zona ni sus cambios DST.

**TR-03 — Fecha de jornada.** `WorkSession.session_date` permanece como la fecha local de **inicio** de esa WorkSession. No se recalcula si pasa medianoche o cambia el huso del dispositivo posteriormente.

**TR-04 — «Today» por supervisor.** El día local actual se calcula por supervisor usando su zona operativa confiable; queda prohibido aplicar a todos el offset de la última WorkSession de la compañía o el del navegador administrativo. Para un supervisor sin jornada ese día, no inferir la zona a partir de otro usuario.

**TR-05 — Fecha/periodo en User Activity.** Los filtros existentes (`day`/`week`/`month`/`year`, fecha ancla, supervisor) deben seguir consultando y agrupando jornadas según `session_date` y la definición vigente de Activity; documentar expresamente esa semántica. No redistribuir viajes o actividades a otros días por su timestamp de ocurrencia sin decisión adicional del PO.

**TR-06 — Horas mostradas.** Los horarios operativos de un supervisor deben formatearse en la **zona correspondiente a la jornada/evento**, no en la del navegador del administrador. Mostrar una referencia de zona u offset no ambigua mediante los formatos/componentes **ya existentes**. No etiquetar `ET`, `EST` o `EDT` a partir de un mero offset cuando no se conoce la zona IANA.

**TR-07 — Ausencia de zona confiable.** No utilizar UTC ni el offset de otro supervisor como si fueran hora local de una persona. Manejar y documentar explícitamente la condición «zona horaria no determinada», preservando los datos existentes. La política de fallback debe aprobarla el PO; no inventar una zona basada en tenant, IP, estado, GPS o navegador administrativo.

**TR-08 — DST.** Usar reglas históricas de la zona IANA cuando esté disponible. Un instante absoluto debe producir la fecha y hora local correcta antes, durante y después del cambio de DST. Las horas locales ambiguas o inexistentes requieren manejo explícito; **no resolver retroactivamente P-2** en este checkpoint.

**TR-09 — Offline.** Mantener el instante de ocurrencia original, la asociación a WorkSession y la fecha de jornada correspondiente al contexto de esa sesión. El instante de recepción/sincronización no reemplaza el de ocurrencia. No vaciar ni reescribir la cola `cer-route-offline` / `pending_actions`.

**TR-10 — Contrato de reportes.** Distinguir **fecha operativa de jornada**, **instante del evento** y **hora local presentada**. Los agregados (millas, actividades, estados de cálculo) deben conservar sus reglas y no alterarse por conversiones horarias de visualización.

## 4. Scope — entregables funcionales de T-1/T-2

### T-1 — Determinación correcta de la fecha operativa

1. Trazar los productores/consumidores de `business_day()`, `session_date` y `start_utc_offset_minutes` en Live, WorkSessions, Activity Explorer y flujos asociados.
2. Eliminar **la dependencia entre supervisores** al resolver «hoy». Un supervisor en zona Central no puede cambiar la fecha utilizada para otro en zona Eastern.
3. Resolver la fecha local actual por supervisor con una fuente IANA confiable; **si la fuente aún no existe, aplicar la puerta de decisión del §6 antes de crear campos o reglas nuevas**.
4. Conservar una WorkSession que atraviesa medianoche en su `session_date` original. No tratarla como olvidada ni cerrarla automáticamente.
5. Preservar los totales y la consolidación de H-2 y R-1. Precisar y probar la diferencia entre:
   - **estado Live de una sesión activa** (puede haber iniciado ayer);
   - **métricas del día** atribuidas por `session_date`.
   No cambiar silenciosamente el alcance temporal de los acumulados; cualquier cambio de negocio no aprobado se eleva como decisión.
6. La selección administrativa de una fecha/periodo explícitos en User Activity conserva su significado actual; no imponer a todos «la fecha local de quien consulta».

### T-2 — Presentación coherente de las horas

1. Centralizar o reutilizar la conversión/formato existente, evitando reglas duplicadas entre Today y User Activity.
2. Aplicar la zona correcta a horarios de jornadas, viajes y actividades expuestos en las vistas existentes, según alcance real del código.
3. Verificar que el navegador en Georgia, Texas o en otra zona muestra la **misma hora local operativa del supervisor** para el mismo evento.
4. Conservar los labels, las pantallas y el layout ya aprobado. Cambiar sólo el valor representado y, **cuando exista un lugar apropiado**, su aclaración de zona/offset; no añadir tarjetas, columnas, menús, selectores o pantallas nuevos.
5. Conservar orden cronológico y duración basados en instantes reales; no calcular duraciones restando horas locales formateadas.
6. Proteger el caso histórico sin zona IANA: no presentar como certeza una conversión que no está soportada por los datos; documentar el tratamiento y sus límites.

## 5. Componentes a reutilizar y límites de arquitectura

Examinar/reutilizar donde corresponda (rutas exactas sujetas a verificación en el repositorio vigente):

- `app/routers_api/live/dao.py`, `router.py`, `schemas.py`.
- `WorkSession`, `WorkSessionsDAO` y servicios actuales de inicio/cierre.
- `ActivityExplorer`, sus filtros y contratos temporales.
- Formateadores actuales de RouteLive y RouteActivityExplorer.
- Captura actual de offset y timestamps de los flujos operativos.
- Auditoría, autorizaciones y middlewares de tenant existentes.

Pertenencia: **CER Route**, no Core de CER ERP. Preferir helpers/contratos temporales compartidos **dentro de CER Route**, sin acoplar los modelos internos de módulos ajenos.

## 6. Puerta de decisión obligatoria: fuente confiable de zona IANA

La auditoría previa no identificó una zona horaria IANA persistida para el supervisor; `start_utc_offset_minutes` es insuficiente para inferir DST futuro y la fecha local actual de un supervisor sin WorkSession reciente.

**Antes de desarrollar los cambios que dependan de esa fuente**, presentar una verificación breve y concreta:

1. ¿Hay una zona IANA ya disponible mediante un perfil, una configuración o un contrato confiable en el código vigente? Identificar ruta, campo y quién la establece.
2. Si **no existe**, proponer el **mínimo modelo persistente necesario** y su estrategia de obtención/validación para:
   - supervisor sin jornada actual;
   - supervisor que trabaja en otro huso;
   - zona aplicable al historial de una WorkSession aunque el perfil cambie después;
   - transición DST y fechas locales ambiguas.
3. **Recomendación para evaluación, no requisito ya aprobado:** zona operativa IANA por usuario/supervisor y referencia de zona de la jornada al iniciarla (snapshot cuando sea necesario para preservar historia), reaprovechando los campos existentes. Comparar con una alternativa equivalente de menor impacto si existe.
4. Documentar impacto del esquema, contrato API, onboarding/configuración sin rediseños, origen de la zona, validación server-side, migración compatible y fallback de históricos.
5. Solicitar aprobación explícita del PO **antes de migrar datos, crear campos, aceptar una zona de dispositivo como verdad operativa o añadir controles de configuración**. El desarrollador no decide unilateralmente zona por defecto, reasignación histórica ni campos sensibles.

Esta puerta de decisión **es una etapa interna de T-1/T-2**, no otro checkpoint. Mientras se resuelve, se pueden preparar pruebas y cambios no dependientes, pero **no declarar T-1/T-2 Completed** sin una resolución trazable.

## 7. Roles / Security / Audit

- La zona operativa y fecha de cada supervisor se resuelven dentro de su tenant. Mantener aislamiento por `company_id`, autenticación, capacidades y scope server-side.
- No confiar únicamente en zona, offset o reloj provistos por el cliente para decidir permisos, elegibilidad, duración crítica o modificación retrospectiva.
- No ampliar `route.live.read`, `route.activity.read` ni permisos del rol Administrador para corregir horas.
- No modificar timestamps ni eventos históricos. Si se introduce configuración temporal, preservar quién la definió/modificó y cuándo, reutilizando auditoría existente.
- Identificar diferencias entre hora de ocurrencia y hora de recepción en las operaciones offline sin reescribir las evidencias.

## 8. Out of Scope / Do Not Change

- **P-2**: detección/resolución/cierre retrospectivo de jornadas olvidadas; permanece en espera hasta certificar T-1/T-2.
- **H-3**: nueva semántica Current/Last Activity.
- **H-1**: filtro móvil de supervisores.
- Rediseño Web/Mobile, nuevas rutas, nuevas opciones en menú o modificaciones de navegación.
- Reglas de kilometraje, odómetro, inicio/cierre de viajes, estados de actividad, sincronización offline o motor de permisos.
- Reasignar automáticamente viajes entre WorkSessions o fechas, cambiar `session_date` histórico, reconstruir timestamps o aplicar conversiones masivas.
- Crear cierres automáticos o usar la hora de sincronización como hora de ejecución.
- Resolver el fallo preexistente `test_provisioning_alignment` dentro de este checkpoint.

## 9. Edge Cases que deben tratarse

- Dos supervisores del mismo tenant en `America/New_York` y `America/Chicago` cerca de medianoche, con fechas locales distintas.
- Supervisor sin WorkSession del día o sin zona IANA identificable.
- WorkSession que comienza antes de las 00:00 y termina al día siguiente.
- Usuario que cambia de zona operativa entre jornadas; visualización histórica sin reatribuir la zona de jornadas previas.
- Instantes alrededor de cambio DST: salto de primavera y repetición de hora de otoño.
- Navegador administrativo en zona distinta de la del supervisor.
- Sync offline retrasado que llega al servidor al día siguiente.
- Varias WorkSessions en una misma `session_date` y consolidación H-2.
- Fechas explícitas y filtros día/semana/mes/año de User Activity.
- Bases/sesiones PostgreSQL con zona diferente de UTC: el resultado no debe depender de la zona de sesión.
- Zona desconocida de registros históricos: mostrar límites explícitos, nunca atribución inventada.

## 10. Acceptance Criteria

**AC01.** El día mostrado/consultado para un supervisor no depende de la última WorkSession de otra persona ni del timezone del servidor.

**AC02.** Dos supervisores en zonas distintas pueden tener fechas locales distintas en el mismo instante sin que uno afecte al otro.

**AC03.** Una WorkSession nocturna mantiene `session_date` y se conserva su continuidad operativa; no se cierra automáticamente.

**AC04.** Los instantes de Start Work, End Work, Trips y ActivityExecution se preservan; únicamente se interpreta/formatea su hora local correctamente.

**AC05.** Las horas mostradas al administrador corresponden a la zona operativa del supervisor/jornada y no varían al cambiar la zona del navegador que consulta.

**AC06.** Las fechas y filtros existentes de User Activity permanecen consistentes con `session_date`; no se alteran totales ni se duplican viajes/actividades.

**AC07.** Today H-2 conserva una fila por supervisor y sus agregados; R-1 conserva detalle conciliable y el contador de actividades reales.

**AC08.** DST y cambios de zona se resuelven de modo determinista cuando se dispone de IANA; no se inventan zonas para históricos.

**AC09.** Las acciones offline conservan su instante y su WorkSession original al sincronizar; no se altera la cola del dispositivo.

**AC10.** Se mantienen roles, tenant isolation, navegación e interfaces ya aprobadas.

**AC11.** Si la fuente de zona confiable requiere nuevos datos/esquema, existe aprobación PO explícita y migración compatible antes de declararlo implementado.

**AC12.** Pruebas automatizadas y E2E demuestran la consistencia temporal real y ausencia de regresiones, con evidencia concreta.

## 11. Tests Required

Preparar integración, regresión y E2E (desktop y mobile donde aplica), como mínimo para:

1. Misma hora UTC, fechas locales diferentes: Eastern vs Central cerca de medianoche.
2. Supervisor sin actividad/jornada actual: tratamiento correcto sin heredar offset ajeno.
3. Dos WorkSessions mismo día y resumen H-2 consistente.
4. Jornada que cruza medianoche, vinculada a la fecha local de inicio.
5. Admin con navegador en otra zona; mismo evento con hora operativa estable.
6. Cambio DST de primavera y otoño, sin ambigüedad en instantes persistidos.
7. Viaje y actividad con instantes válidos: cronología y duración intactas.
8. Evento offline capturado ayer y sincronizado hoy: ocurre ayer, conserva WorkSession y `session_date`.
9. User Activity en día/semana/mes/año: filtros, resúmenes y detalle conciliables.
10. Zona IANA ausente/incorrecta y casos históricos: fallback aprobado, sin datos inventados.
11. Tenant/scope/autorización, incluidas solicitudes con identificadores ajenos.
12. Regresión dirigida de Start Work/End Work, Trips, ActivityExecution, mileage, Today, User Activity y caché del contrato donde corresponda.

**Validación decisiva:** contrastar un mismo evento desde dos navegadores en zonas diferentes y comprobar que la hora operativa del supervisor es idéntica. Contrastar dos supervisores en husos distintos alrededor de medianoche y comprobar que su día local se determina por separado.

## 12. Checkpoint / Delivery & Definition of Done

Entregar **un solo MD de implementación T-1/T-2**, incluyendo:

- **AS-BUILT** temporal inicial (fuentes, rutas, API y usos de `business_day()`).
- Fuente IANA finalmente seleccionada y **evidencia de aprobación PO** si requirió datos/esquema/configuración adicional.
- **Expected → Implemented → Evidence → Gap** para AC01–AC12.
- Archivos, contratos, modelo de datos y migraciones efectivas (si se aprobaron).
- Pruebas y resultados, incluidos casos Eastern/Central y DST.
- Capturas/observaciones E2E sin cambios estructurales de UI.
- Regresiones y limitaciones históricas/operativas.
- Rama, MR, commit SHA, despliegue requerido y estado de fusión.

Clasificar el resultado **Completed / Partial / Blocked / Pending Validation** según evidencia, sin declarar completado sólo porque compile.

**Definition of Done:** la aplicación interpreta el día de cada supervisor y presenta sus horarios operativos de forma coherente, verificable e independiente de la zona del administrador y del servidor; conserva jornadas nocturnas, registros y agregados; y dispone de una fuente temporal confiable aprobada que permite desarrollar posteriormente P-2 sin conjeturas.

**Regla de gobierno:** no iniciar P-2, H-3 ni H-1 como parte de este trabajo. No fusionar ni desplegar cambios sin autorización del flujo de certificación de CER.
