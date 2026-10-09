# CER Route — T-1/T-2 · Respuesta del Product Owner a Decision Gate 001

**Referencia:** `CER_ROUTE_T1_T2_TIMEZONE_DECISION_GATE_001.md` (09-oct-2026)  
**Checkpoint:** T-1/T-2 — Timezone & Business Day  
**Estado:** **D1–D6 APROBADAS CON PRECISIÓN DE PRECEDENCIA. AUTORIZADA LA IMPLEMENTACIÓN DE T-1/T-2.**  
**Rama / MR existente:** `feature/t1-t2-timezone-business-day` / `!79`  

## 1. Decisión de producto

Aprobamos la **opción A adaptada: detección automática por defecto y configuración administrativa opcional exclusivamente para excepciones**.

El supervisor **no debe tener que configurar manualmente su zona horaria** para utilizar CER Route. Al iniciar una jornada, el sistema detectará la zona IANA del dispositivo (`Intl.DateTimeFormat().resolvedOptions().timeZone`), la validará server-side y fijará la zona efectiva de esa WorkSession.

El administrador podrá configurar una zona operativa IANA en **el panel existente del supervisor**, pero ese campo será **opcional**, estará vacío por defecto y actuará como una **excepción explícita**. No crear pantallas, menús ni un procedimiento de configuración obligatoria por supervisor.

La zona del dispositivo es evidencia de configuración del equipo, **no prueba de ubicación GPS**.

## 2. Resolución de D1–D6

| Decisión | Resolución aprobada |
|---|---|
| **D1 — Modelo** | **A adaptada.** Autorizar `supervisor_profile.operational_time_zone` y `work_session.start_time_zone`, ambos nullable; migración aditiva, sin backfill. |
| **D2 — Dispositivo** | **Sí.** Capturar automáticamente IANA del dispositivo al iniciar la jornada y al encolar Start Work offline; validar contra `zoneinfo`. Fuente predeterminada cuando no exista override administrativo. |
| **D3 — Zona indeterminada** | Nunca usar la zona de otro supervisor ni presentar UTC como si fuera su hora local. Mostrar estado disponible; si no puede determinarse su día local, indicarlo discretamente como **zona no determinada**, sin inventar una fecha operativa confiable. |
| **D4 — Jornada nocturna** | Una WorkSession activa permanece visible en Today después de medianoche; sus métricas se atribuyen a su `session_date` original. No trasladar millas o actividades al día siguiente. |
| **D5 — Históricos** | Mantener registros intactos. Cuando sólo exista offset histórico, mostrarlo explícitamente (`UTC-04:00`, etc.), sin atribuirle una zona IANA ni prometer exactitud ante cambios DST que ese offset no permita reconstruir. |
| **D6 — Perfiles existentes** | **No** realizar asignaciones masivas. La zona administrativa sólo se configura manualmente cuando exista una excepción. En el resto, captura automática en jornadas futuras. |

## 3. Regla de precedencia obligatoria — evitar fechas inconsistentes

**Una sola zona efectiva por WorkSession**, que se utilizará **tanto para calcular `session_date` al iniciar como para presentar los eventos de esa jornada**:

1. Si `supervisor_profile.operational_time_zone` tiene un IANA válido, **prevalece como override administrativo explícito**.
2. Si no hay override, usar la **zona IANA detectada en el dispositivo** al iniciar la WorkSession.
3. Guardar la **zona efectiva que realmente se aplicó** en `work_session.start_time_zone` como instantánea inmutable de esa jornada. No escribir siempre la del dispositivo cuando haya override, porque produciría una contradicción con `session_date`.
4. Calcular `session_date` a partir del **instante de inicio + zona efectiva**; congelarla durante toda la jornada, aunque cruce medianoche o cambie la configuración del supervisor.
5. Conservar `start_utc_offset_minutes` como evidencia existente. No sustituir instantes `timestamptz` ni reescribir historias.

**Ejemplo de discrepancia:** perfil con override `America/Chicago`, teléfono en `America/New_York`. La WorkSession usa **America/Chicago** tanto para `session_date` como para el formato de horas. Si se desea la zona real detectada del teléfono, se deja vacío el override. La UI debe identificar la zona efectiva cuando sea necesario para evitar interpretaciones equivocadas.

**Today sin WorkSession actual:** usar override explícito si existe; en su defecto, la **última zona IANA efectiva de ese mismo supervisor**, si está disponible y resulta apropiada como referencia provisional; de lo contrario, **zona indeterminada**. Nunca tomar el offset o la zona de otra persona, ni extrapolar un offset histórico fijo a una fecha con DST diferente. Si un perfil tiene jornada activa, mostrar su estado vivo aunque su `session_date` sea anterior al día local actual.

**User Activity:** los filtros y agrupaciones mantienen el `session_date` persistido de cada jornada. Los timestamps de las tarjetas se formatean según la zona efectiva de la WorkSession correspondiente, **no la zona del navegador del administrador**.

## 4. Condiciones técnicas y controles

- **Esquema autorizado:** sólo las **dos columnas nullable** justificadas en D1; migración reversible y sin actualización retroactiva de datos. Cualquier otro cambio persistente requiere justificación y aprobación previa.
- **Validación:** zona IANA reconocida por `zoneinfo`; configuración administrativa inválida → rechazo con validación del API. Si el dispositivo no proporciona una zona válida, mantener operación compatible con evidencia temporal disponible, pero no etiquetarla como IANA fiable ni atribuir certeza inexistente.
- **Auditoría y permisos:** cambios de override administrativo con permiso server-side por tenant y audit trail (quién, cuándo, valor anterior/nuevo). El supervisor no puede modificar la zona operativa de otros usuarios.
- **Offline:** capturar la zona del dispositivo junto con el instante del evento **al encolar**, no al sincronizar. La sincronización no debe modificar fechas o instantes originales. Si la configuración administrativa pudiera cambiar entre encolado y sincronización, implementar una resolución que no reinterpreté silenciosamente la jornada; documentar y probar el caso.
- **DST:** utilizar IANA y reglas históricas de `zoneinfo`, con pruebas de transición de primavera y otoño. Una instantánea histórica no cambia cuando se modifica el perfil.
- **Compatibilidad:** contratos API **aditivos**, preservando los campos/tipos actuales para clientes antiguos. Mantener los 25 campos de instantes como `timestamptz`. No modificar el cálculo de kilometraje ni las reglas funcionales de H-2 y R-1.
- **Interfaz:** único ajuste de configuración permitido: campo **opcional** en el panel actual de supervisor, más las correcciones de presentación temporal propias de T-1/T-2; **sin rediseño ni nuevas pantallas**.

## 5. Implementación, pruebas y entregables

Proceder en la rama / MR existentes con el **checkpoint T-1/T-2 completo**, incluyendo las correcciones D1–D5 identificadas en el diagnóstico y la suite AC01–AC12 del documento original. En particular demostrar:

1. Dos supervisores en Este y Centro ven fechas locales correctas, sin dependencia de la última WorkSession de otro.
2. **Default automático** sin perfil configurado; **override explícito** distinto del dispositivo; cambio posterior de override sin modificar sesiones históricas.
3. `session_date`, Today, User Activity y horas de tarjetas utilizan la **misma zona efectiva de su jornada**.
4. Jornada nocturna activa visible en Today; métricas sin migrarse a otra fecha.
5. Supervisor sin sesiones / zona indeterminada sin UTC engañoso.
6. Históricos sólo con offset, DST de noviembre y marzo, y navegador administrador ubicado en otra zona.
7. Start Work offline, sincronización diferida e incompatibilidad potencial entre zona al encolar y zona al sincronizar.
8. Tenant isolation, permiso de cambio de override, auditoría, regresión de Start Work / End Work, H-2 y R-1.
9. Pruebas con fechas/instantes explícitos; corregir únicamente fixtures E2E que dependan erróneamente de `CURRENT_DATE`, sin alterar requisitos ni aserciones de negocio.

**Entrega:** un único MD AS-BUILT / Expected vs Implemented / evidencia, con archivos afectados, migración, contratos, pruebas, limitaciones, capturas, commit SHA y MR. Clasificar faltantes como PENDING VALIDATION o BLOCKED, nunca como Completed por declaración.

**Control de gobierno:** **No fusionar ni desplegar el MR sin certificación del Product Owner.** No implementar P-2, H-3 ni H-1 en este checkpoint.

**No emitir un nuevo Decision Gate para volver a preguntar D1–D6.** Si aparece un obstáculo técnico material no cubierto por estas decisiones, presentarlo puntualmente con impacto y alternativas, sin ampliar el alcance por cuenta propia.
