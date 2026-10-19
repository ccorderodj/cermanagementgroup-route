# RTE-MAIL-CP4-01 — Programacion automatica y Cron Job en DigitalOcean

**Producto:** CER Route  
**Modulo responsable:** CER Route / Activity Emails (infraestructura de correo compartida)  
**Version:** 1.0 | **Fecha:** 2026-10-19  
**Tipo:** instruccion ejecutable para programador y agente de desarrollo  
**Dependencia coordinada:** `RTE-MAIL-CP4-02_ON_DEMAND_REPORT_FALLBACK_V1_0.md`  
**Decision de entrega:** desarrollar y validar; **NO habilitar envios masivos o unattended en produccion hasta GO del Product Owner**.

## 1. Context / evidencia primaria

Fuentes del proyecto:
- `RTE-MAIL-UNIFIED-01_TEST_SEND_AND_STRATEGIC_REPORTS_V1_1.md`: contrato de los cuatro tipos de reportes, reglas de jerarquia, confidencialidad y acumulado semanal.
- `RTE-MAIL-UNIFIED-01_CP1_REPORT.md`: politica de pruebas unificada, `mail_test_send`, proveedor, controles y migracion `0022_mail_test_send`.
- `RTE-MAIL-UNIFIED-01_V1_2_C_CP3_REPORT.md` (16-10-2026): T0 a T4 implementados y probados en local; strategic templates y destinatarios implementados segun reporte; migracion `0023_strategic_reports` reportada; **CP4 no implementado** y **recepcion externa real pendiente**.
- `RTE-MAIL-TEST-01_EXISTING_MAIL_VALIDATION_REPORT.md`: `app/core/platform/scheduler.py` contiene APScheduler y control de lider por PostgreSQL; NO existe, segun esa auditoria, job de Activity Emails ni registro de entrega productiva.

**Estatus verificable:** estos informes documentan el repositorio revisado, no prueban que el despliegue actual de DigitalOcean tenga ya la ultima rama, migraciones, proveedor funcional o las cuatro plantillas. Inspeccionar el estado actual de codigo y App Platform antes de cambiar algo; registrar AS-BUILT / GAP / DEVIATION.

**Fuente externa DigitalOcean (consultada 19-10-2026):** https://docs.digitalocean.com/products/app-platform/how-to/manage-jobs/ . App Platform ofrece `jobs.kind: SCHEDULED`, `schedule.cron`, `schedule.time_zone` y una **frecuencia minima de 15 minutos**. Un cron cada 15 minutos NO garantiza por si solo `End Work + 20 minutos` exactos.

## 2. Objective

Dejar operativa y observable la programacion de correos para los **cuatro** mensajes aprobados, reutilizando la misma configuracion de proveedor, plantillas, scopes y generadores usados por Preview/Send test. Configurar en la **misma DigitalOcean App Platform de CER Route** un componente Scheduled Job recuperador de envios vencidos. No duplicar ni el servicio de correos ni el motor de reporte.

La ejecucion automatica debe tolerar caidas/reinicios, cambios de replica, reintentos de proveedor, concurrencia, ejecucion manual y desfases de la infraestructura **sin duplicar mensajes**.

## 3. Current state — inspeccion obligatoria antes de editar

Solicitar y documentar: nombre/ID de App Platform, branch/commit desplegado, app spec actual, componentes de `jobs`, Dockerfile/build, `run_command`, `APScheduler` real, fuente de datos y migraciones, proveedor `email` y fallback, roles/permisos actuales, rutas UI/API Activity Emails, preferencias, jerarquia, servicios de agregacion y permisos de notas. **No extraer ni imprimir secretos**.

Verificar si hay algun cron existente para Route o para el correo y si algun servicio web ya despacha notificaciones; evitar doble ejecucion. Entregar un inventario Expected -> Implemented -> Evidence -> Gap antes de la migracion/despliegue.

## 4. Scope

1. Elegibilidad y generacion de vencimientos (`due_at`) para los cuatro tipos de correo.
2. Un unico servicio compartido de planificacion/dispatch para ejecucion puntual, conciliacion por cron y futura solicitud manual (CP4-02).
3. Registro durable de envios, reserva/concurrencia, idempotencia, estados, reintentos, omisiones y auditoria.
4. Configurar un **Scheduled Job de DigitalOcean** en la app existente para recuperar/conciliar envios vencidos cada 15 minutos.
5. Usar el `PlatformScheduler` existente para disparos de mayor precision, **solo si** su ciclo de vida y lider unico son aptos; si no, proponer alternativa de worker persistente, con evidencia, **antes de aprobar una degradacion a 15 minutos**.
6. Implementar verificaciones de salud, ejecuciones monitorizables, pruebas con reloj inyectable, simulacion de fallos y runbook de DO.
7. Coordinarse con el boton manual CP4-02 mediante un contrato unico de entrega.

**Out of scope:** redisenar Activity Emails, editar el texto aprobado de las cuatro plantillas, reescribir `End Work`, cambiar jerarquia/roles, mostrar datos GPS en correos motivacionales, utilizar IA para calculos, crear otra app DigitalOcean, ejecutar remesas masivas sin autorizacion, enviar notas reales mientras DP-NOTES no este resuelto.

## 5. Matriz de mensajes y reglas de vencimiento

| Clave funcional | Destinatario | Disparador | Contenido obligatorio | Condiciones |
|---|---|---|---|---|
| `MIDDAY_MOTIVATION` | Usuario habilitado | 12:00 hora local aplicable | Recordatorio individual hasta corte; sin notas ni ubicaciones | Al menos 1 actividad elegible completada; si no, omitir y registrar motivo |
| `END_OF_DAY_RECOGNITION` | Usuario habilitado | **20 min tras `End Work` valido** | Resumen del dia + acumulado semanal personal | `End Work` confirmado; si reanuda dentro de 20 min, invalidar vencimiento viejo y recalcular; actividades elegibles requeridas |
| `STRATEGIC_MIDDAY_REPORT` | Mando autorizado y habilitado | 12:00 hora local del reporte | Seccion por cada descendiente autorizado: Activity Breakdown + Activity Details del dia hasta el corte | Respetar jerarquia efectiva en el corte, tenant, scopes y reglas de notas; no incluir total semanal del equipo |
| `STRATEGIC_END_OF_DAY_REPORT` | Mando autorizado y habilitado | 20 min tras confirmarse el **ultimo cierre conocido del equipo**, o **hora maxima configurable** | Por persona: breakdown del dia, detalles del dia, acumulado semanal; **un unico `Team Weekly Summary` al final** | Si cierre completo no es demostrable, esperar al cutoff; no auto-cerrar jornadas; no duplicar subordinados ni eventos |

**Reglas transversales:**
- Maximo **un envio automatico/logico por tipo, destinatario, tenant y dia operativo** (excepto reenvio explicito autorizado y auditado en CP4-02). Una persona puede tener dos tipos habilitados, y un mando tambien recibir el motivacional sin mezclar destinatarios ni alcances.
- Todas las preferencias de nuevos destinatarios siguen **OFF por defecto**. Volver a validar elegibilidad, rol, grants, correo de destino y plantilla al momento de enviar; no confiar en snapshots de permisos anteriores.
- Mantener `session_date` para jornadas que cruzan medianoche y datos `timestamp with time zone` para los instantes; no suponer que el cambio a 00:00 implica cierre. Manejar DST, dias sin sesion, vacaciones, y zonas horarias distintas de usuario/mando.
- En el estrategico, el CEO cubre los descendientes de su jerarquia (Sales si depende de CEO); COO no incluye Sales cuando depende directamente del CEO. Los reportes no incluyen por defecto trabajo propio del mando. De ser necesario, confirmar el contrato frente a los grants existentes sin ampliar privilegios.
- No crear campos de metricas duplicados. Reutilizar Activity Breakdown, servicios de actividad, redondeos y reglas existentes. Donde falte dato fiable mostrar `No disponible`, nunca `0` inventado.
- **DP-WEEK**: inicio de semana **lunes recomendado, no aprobado**; parametrizar o documentar el gate. **DP-TIMEZONE**: definir zona confiable del destinatario/reporting y corte por fecha operativa. Si faltan, bloquear activacion real para los reportes afectados.
- **DP-NOTES**: ninguna nota libre real se exporta por correo hasta aprobar whitelist/roles/privacidad. Mientras tanto, omitirla o usar `Detalle no incluido en el correo`; no bloquear la construccion del motor por esa razon.
- **DP-CUTOFF**: hora maxima estrategica configurada por tenant o destinatario segun diseno existente; NO inventar `19:00` ni activarla sin seleccion expresa del PO. Si no hay corte, el reporte estrategico final no puede declararse listo para produccion.

## 6. Diseno esperado — no prescribir implementacion interna no necesaria

### 6.1 Un motor de reportes y un motor de entrega

Definir una interfaz logica equivalente a:

- `build_report(report_type, recipient_id, operational_date, as_of, mode)` que aplica jerarquia, permisos, datos, redaccion de notas, plantilla almacenada y zona temporal; el mismo servicio sirve a Preview/Test, automatico y manual, diferenciando **datos demo** de **datos reales**.
- `schedule_or_claim_delivery(tenant, recipient, type, operational_day, source)` con estado durable y **llave de idempotencia compartida por cron, scheduler y boton manual**.
- `dispatch_due_deliveries(now, source)` revalida todo antes de llamar al proveedor; no admite destinatarios arbitrarios de una solicitud externa.

Nombres/rutas/APIs concretos los decide el desarrollador al verificar el repositorio. Evitar que un modulo consulte tablas privadas de otro por fuera de sus servicios autorizados.

### 6.2 Ledger durable y transiciones

Crear o reutilizar tabla productiva diferente de `mail_test_send` (que es exclusiva de tests), con tenant, recipient canonical ID, report type, operational_date, corte/ventana, planned_due_at, status, attempt_count, last_attempt_at, provider/backend, accepted_at, requester/source (`schedule`, `reconcile`, `manual`), outcome, error_code sanitizado, version de plantilla, timestamp de creacion/actualizacion, y audit actor para acciones manuales. Guardar **solo lo minimo**: no contenido de notas ni secretos en los logs. Proteger datos sensibles que no puedan evitarse.

Estados recomendados: `PENDING` -> `CLAIMED` -> `ACCEPTED_BY_PROVIDER`, `RETRYABLE_FAILURE`, `PERMANENT_FAILURE`, `SKIPPED`, `UNKNOWN_OUTCOME`. Si un proveedor confirma que acepto el mensaje, **no reintentar automaticamente** el mismo envio; `accepted` no equivale a `delivered`. Si hay timeout tras transmitir y no se sabe si fue aceptado, usar `UNKNOWN_OUTCOME` y proceso seguro de conciliacion, no un reenvio ciego.

Unique index transaccional para la llave logica de entrega. CLAIM con lock/lease atomico y caducidad/recovery; reintentos acotados con backoff; perdidas de corrida recuperables, sin duplicados en carrera entre web, APScheduler, cron, replicas y boton. Garantizar que `manual` cumple/cierra el mismo envio pendiente cuando opera como fallback; antes de cutoff, un preview no consume esa llave. Probar corrida simultanea real.

### 6.3 Orquestacion combinada y precision

- **Registro del vencimiento:** `End Work` valido genera o actualiza durablemente su entrega `END_OF_DAY_RECOGNITION` con vencimiento +20; `Keep working`/reapertura invalida o pospone el vencimiento previo. El trabajo de envio no debe bloquear la respuesta de `End Work` ni cambiar el flujo aprobado.
- **Estrategico:** cuando existe evidencia confiable de ultimo cierre del equipo programar +20; si la completitud es incierta, esperar la hora maxima configurada; no concluir por ausencia de `End Work` que el usuario ha terminado.
- **Mediodia:** evaluar la hora local de cada destinatario y registrar una entrega con corte exacto de 12:00; si la corrida se demora, la ventana de datos sigue cerrando a las 12:00, no se convierte en un conteo arbitrario hasta la hora real de envio.
- **Precision:** verificar que el APScheduler existente puede disparar actividades individuales a tiempo (+20) sin ejecutar el job en todas las replicas; usarlo para el ciclo oportuno si es correcto. El DO cron es un **reconciliador** que recoge envios vencidos u omitidos en lugar de ser el unico reloj; con cron solo, una entrega puede esperar hasta la siguiente ventana de 15 minutos y eso **no cumple** la condicion de exactitud ya acordada.
- **Crash recovery:** al reiniciar, reconstruir/recuperar pendientes de la BD, sin repeticiones; considerar un `End Work` ya realizado que no genero una reserva por fallo parcial. Nunca crear envios antiguos ilimitados por primera activacion: fijar politica y ventana de recuperacion aprobadas (DP-RECOVERY).

## 7. DigitalOcean App Platform — configuracion requerida

**No configurar un nuevo proyecto DO ni cron del sistema operativo dentro de `uvicorn`.** Configurar un componente **Job -> On a schedule** en la **App existente**. Confirmar rama, source_dir, Dockerfile y build identicos/compatibles con el web service; compartir acceso seguro a Postgres y a las credenciales del proveedor mediante los mecanismos existentes de secretos. No compartir secretos en un MD o en un screenshot.

- En App Platform: **Apps > [CER Route app] > Add components > Create resources from source code > [repositorio/rama] > Resource type: Job > Deployment settings: Run command > Job trigger: On a schedule**.
- `cron: "*/15 * * * *"`, `time_zone: Etc/UTC` para el sweep de conciliacion; **las zonas horarias de destinatarios se calculan en el dominio, no en la TZ del job**. El desarrollo puede seleccionar otra expresion si documenta por que es equivalente/mas apropiada.
- Comando: reutilizar el entrypoint de jobs que exista. Si no existe, implementar uno de proceso unico (`--once`, despacho de vencidos, exit code real, sin levantar servidor HTTP ni arrancar un segundo APScheduler). Ejemplo conceptual **NO copiar sin comprobar rutas reales**: `python -m app.jobs.mail_dispatch --mode reconcile --once`.
- Guardar cambios en la app spec bajo control de versiones/IaC si existe, NO reemplazar la spec completa por un fragmento. Ejemplo **parcial** para integrar tras verificar:

```yaml
jobs:
  - name: route-mail-reconcile
    kind: SCHEDULED
    schedule:
      cron: "*/15 * * * *"
      time_zone: Etc/UTC
    # Incorporar fuente Git/Docker, run_command, tamano y envs
    # VALIDADOS contra el app spec real. No desplegar este fragmento solo.
```

- Promover primero en desarrollo/staging con `MAIL_AUTOMATION_ENABLED=false` y `MAIL_AUTOMATION_DRY_RUN=true` (nombres sugeridos, adaptar al sistema); despues GO habilitar gradualmente por tenant y tipo, nunca todos por defecto.
- Documentar donde se consultan **Activity > Jobs**, logs de invocaciones y alertas de job fallido; registrar run_id, conteos por `due/claimed/accepted/retry/skipped/unknown`, duracion y drift sin PII.
- Probar que las ventanas de cron no se solapan peligrosamente; agregar lock/transaccion y timeout razonable. La consola y API de DO deben evidenciar cron registrado y ejecuciones.

Documentacion oficial DO: https://docs.digitalocean.com/products/app-platform/how-to/manage-jobs/ ; App Spec: https://docs.digitalocean.com/products/app-platform/reference/app-spec/ .

## 8. Security / audit / operational safety

Autenticacion y autorizacion server-side en origen de preferencias/reportes; minimo privilegio y separacion de tenant; no exponer endpoint publico sin autenticar para el cron. Jobs corren con credenciales restringidas y secreto de proveedor reutilizado; no imprimir env vars ni payloads. Outbound permitido solo a usuarios verificados y habilitados bajo scope vigente. Historial de cambios de preferencias/horario/corte y de tentativas de entrega: quien, que, cuando, resultado y razon para envios manuales. El correo estrategico nunca incluye notas/PII prohibida ni destinos fuera del usuario receptor configurado.

Preparar `kill switch` global y por tipo/tenant. Si falla DO cron, la interfaz debe poder generar/reponer el reporte mediante CP4-02; **la generacion local no equivale a capacidad de enviarlo si el proveedor esta caido**.

## 9. Acceptance criteria

| ID | Evidencia exigida |
|---|---|
| CR-01 | Inventario del repo/DO, app spec, estado despliegue/proveedor/migraciones y decision sobre APScheduler previa al cambio |
| CR-02 | Un Scheduled Job `SCHEDULED` real en la misma App, cada 15 min, comando unico `--once`, logs y captura de al menos dos invocaciones |
| CR-03 | Las **cuatro** variantes calculan `due_at` y renderizan usando plantillas guardadas; no confundir T0 (correo de proveedor) con un correo automatico |
| CR-04 | Mediodia: corte local 12:00; dos usuarios en zonas distintas y cambio DST con resultados correctos |
| CR-05 | Motivacional fin de dia: envio oportuno en `End Work +20`; reapertura en minuto 19 pospone; no modificar `End Work` ni cerrar jornada nocturna |
| CR-06 | Estrategico mediodia: por descendiente autorizado, sin resumen semanal final; privilegios validados, CEO/COO/Sales correctos |
| CR-07 | Estrategico final: cierre completo o cutoff maximo aprobado; totales individuales semanales y un solo Team Weekly Summary al final, sin dobles conteos |
| CR-08 | Sin actividad: motivacional omitido; sin usuario habilitado/no verificado/rol revocado: no se envia; estados y motivos auditados |
| CR-09 | Ejecuciones simultaneas de scheduler/DO/manual no generan duplicados; 409/estado equivalente ante intento ya reservado/aceptado |
| CR-10 | Fallos auth/red/timeouts/unknown outcome, recuperacion de proceso caido y reintentos se comportan sin secretos ni reenvio ciego |
| CR-11 | Tests con reloj inyectado, base real de integracion, multi-tenant, permisos, DST, medianoche, retries, regresion y E2E admin |
| CR-12 | Capturas/commits/migraciones, runbook DO y **GO de PO separado** antes de habilitar produccion; recepcion en buzon real por tipo |

## 10. Tests Required

Tests de unidad para calculos de vencimiento por zona; simulacion de mediodia, End Work+19/+20/+21, reanudacion, missing/cancelled sessions, equipo que nunca cierra, corte maximo, DST, monday/week-to-date segun DP, entregas en una misma fecha operativa y cambio de asignaciones. Tests DB para unique constraint, stale lease, retries y paralelismo; pruebas de integracion correo con backend falso; E2E mail history/admin; cron DO real en entorno seguro y capturas de `Activity > Jobs` y de logs saneados. Confirmacion de recepcion real separada por los cuatro tipos antes de GO.

## 11. Checkpoints / handoff

- **CP4-01A — Reconocimiento y contrato:** inspeccionar repo + DO, determinar scheduler oportuno y ledger compartido con CP4-02. Entregar decision tecnica y supuestos bloqueantes.
- **CP4-01B — Motor de envio y pruebas:** vencimientos, ledger, idempotencia, reintentos, pruebas de cuatro tipos. No activar salida masiva.
- **CP4-01C — Deploy controlado DO:** job, app spec, evidencia de invocacion, dry-run + pruebas real-mail controladas, runbook y checklist GO/NO-GO.

**No detener todo el desarrollo por decisiones no necesarias para pruebas ficticias**: desarrollar el motor y dejar flags desactivados donde corresponda. No desplegar/provocar envios reales a destinatarios operativos hasta resolver DP-NOTES, DP-TIMEZONE, DP-WEEK, DP-CUTOFF, DP-TEAM, DP-RECOVERY y evidencia de proveedor.

## 12. Deliverables

1. PR/MR con diff focalizado, migraciones reversibles y archivos de configuracion DO versionados.
2. MD de entrega `RTE-MAIL-CP4-01_REPORT.md`: AS-BUILT, Expected -> Implemented -> Evidence -> Gap -> Impact, pruebas ejecutadas/conteos, decisiones pendientes, screenshots/logs y estado del entorno (no confundir local con desplegado).
3. Runbook con comandos reales validados, la cron expression instalada, ruta a logs/jobs, kill switch, procedimiento de recuperacion e instrucciones de rollback.
4. Lista de dependencias contractuales compartidas con CP4-02; no crear otra tabla de control de envios en ese checkpoint.

**Do Not Change:** navegacion aprobada, editor de plantillas y prueba T0-T4, registro `mail_test_send`, flujo Start/End Work y Keep Working, derivacion de datos de otros modulos, formulas de millaje/costos sin autorizacion, roles/jerarquia establecida.
