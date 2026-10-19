# RTE-MAIL-CP4-01 — Programación automática y Cron Job en DigitalOcean

**Reporte** · 19 de octubre de 2026
**Instrucción:** `_cer_delivery/RTE-MAIL-CP4-01_DIGITALOCEAN_CRON_SCHEDULING_V1_0.md`
**Status: PARTIAL.** CP4-01A y CP4-01B completos y probados en local. CP4-01C preparado pero **sin desplegar**.

**Sin desplegar, por tres motivos:**
- el **Scheduled Job** está definido en la App Spec versionada, pero **no** está instalado en DigitalOcean, porque no tengo acceso a la consola;
- **no hay invocaciones reales** del job ni recepción en un buzón;
- **la automatización queda apagada** (`MAIL_AUTOMATION_ENABLED=false`, `MAIL_AUTOMATION_DRY_RUN=true`) hasta el GO del PO.

## 1. CP4-01A: inventario y decisión técnica

| Elemento | Estado | Evidencia |
|---|---|---|
| Rama de trabajo | Desde `dev` `cfa4511`, que incluye MR !99 a !108 | `git log` |
| App Platform | `cerroute-dev`, buildpack Python desde GitLab `dev`, `deploy_on_push`; job `migrate` (PRE_DEPLOY); variables a nivel de App | `_cer_delivery/APP_SPEC_cerroute-dev.yaml`. **UNVERIFIED** contra la spec real: ese archivo es la propuesta del 07-10, y su paso `converge` no parece aplicado en DigitalOcean |
| Programador interno | APScheduler en la app, candado de líder en PostgreSQL (`pg_try_advisory_lock`), tareas registradas antes de `start()` | `app/core/platform/scheduler.py`; los Runtime Logs de DigitalOcean del 16-10 muestran sus tareas cada 30 s y cada minuto |
| Envío de correos de actividad antes de CP4 | **Ninguno**: ni job ni ledger productivo | Reportes RTE-MAIL-TEST-01 y CP3 |
| Proveedor de correo | M365 OAuth configurado; **Verify: «rejected the sign-in»** | Captura del PO del 16-10 |
| Migraciones | Head `0023` antes de este cambio | `alembic heads` |

**Decisión** (tomada antes de cambiar nada):
- **El programador interno da la precisión** (cada minuto, solo el líder). Basta para «End Work + 20 min» con ±1 min, sin degradar a 15 minutos.
- **El job de DigitalOcean es el reconciliador** (cada 15 min, el mínimo de App Platform): recoge lo que no salió si la app estuvo caída.
- **Los dos llaman al mismo despacho** y reservan sobre la misma clave única, compartida con el botón de CP4-02. No hay otra tabla de control.

## 2. CP4-01B: motor de envío
- **`real_reports.generar`:** los cuatro correos con datos reales y la plantilla guardada. Calcula zona, corte, vencimiento, si es parcial o final, y la elegibilidad. Las reglas de la §5:

| Tipo | Vence | Condiciones |
|---|---|---|
| Midday Motivation | 12:00 en la zona del destinatario | Al menos una actividad completada antes de las 12:00; si no, `skipped/no_activity` |
| End of Day Recognition | 20 min después del **último** cierre del día | Todas las jornadas del día cerradas. Abrir otra jornada ese día lo **aplaza solo**, porque se calcula siempre del estado actual |
| Strategic Midday | 12:00 en la zona del mando (o la más frecuente de su equipo) | Un bloque por persona autorizada; sin Team Weekly Summary |
| Strategic End-of-Day | 20 min después del cierre del **último** del equipo, o `MAIL_STRATEGIC_CUTOFF` | Sin cierre completo ni hora máxima, no hay reporte final (DP-CUTOFF no se inventa) |

- **`delivery.despachar_vencidos`:** el barrido.
  - Caduca reservas abiertas (→ `unknown_outcome`).
  - Recorre los interruptores encendidos de cada compañía.
  - Evalúa hoy y, para los de cierre, también ayer (jornadas que cruzan la medianoche).
  - Solo toma lo vencido **dentro de** `MAIL_RECOVERY_WINDOW_HOURS`.
  - Revalida destinatario, permisos, interruptor y tipo habilitado **en el momento**.
  - Reserva, envía y clasifica el resultado.
- **Ledger `activity_email_delivery`** (migración `0024`):
  - clave única `(company, recipient, type, operational_date)`;
  - estados `pending/claimed/accepted_by_provider/retryable_failure/permanent_failure/skipped/unknown_outcome`;
  - reserva de 5 min con su caducidad, intentos y espera (5 min, 15 min, 1 h; máximo 5);
  - motivo con código fijo, quién lo pidió y su motivo, versión de la plantilla.
  - **Sin cuerpo, notas ni texto del proveedor.**
- **Clasificación del resultado:**
  - aceptado → `accepted_by_provider` (no es «entregado») y **no se reintenta**;
  - rechazo del mensaje → `permanent_failure`;
  - tiempo agotado con el mensaje en vuelo → `unknown_outcome`, sin reenvío;
  - credenciales o red → `retryable_failure`;
  - backend de consola (sin proveedor) → `retryable_failure/provider_not_configured`: no cuenta como enviado.
- **Interruptores:** `MAIL_AUTOMATION_ENABLED` (general), `MAIL_AUTOMATION_DRY_RUN` (ensayo: cuenta `would_send` sin escribir), `MAIL_REAL_SEND_TYPES` (por tipo; vacío = ninguno). Más el interruptor de cada persona en Recipients, apagado por defecto.
- **Disparadores:**
  - **programador interno:** `register_activity_email_jobs()` en `main.py`, cada minuto;
  - **job:** `python -m app.routers_api.activityemails.jobs --once`. Exige `--once`, no levanta servidor ni un segundo APScheduler, termina con código 0, o 1 si la pasada falla.

## 3. CP4-01C: configuración de DigitalOcean (preparada, no desplegada)
- **`_cer_delivery/APP_SPEC_cerroute-dev.yaml`:**
  - job `route-mail-reconcile`, `kind: SCHEDULED`, `cron: "*/15 * * * *"`, `time_zone: Etc/UTC`, misma rama, build y tamaño que `migrate`, `run_command: python -m app.routers_api.activityemails.jobs --once`;
  - variables `MAIL_AUTOMATION_ENABLED="false"` y `MAIL_AUTOMATION_DRY_RUN="true"`.
  - Validado como YAML. Hay que **añadir** el bloque a la spec real, no sustituirla.
- **Runbook:** `docs/MAIL_DISPATCH_RUNBOOK.md`. Explica cómo instalar el job (consola o spec), comprobar invocaciones (Activity › Jobs, Runtime Logs, contadores `MAIL DISPATCH`), los interruptores, el kill switch, cómo encenderlo por fases y la vuelta atrás.

## 4. Pruebas (local, base de tests)

| Lote | Resultado |
|---|---|
| `tests/integration/test_activity_email_delivery.py` (compartido con CP4-02) | **19/19 PASS** |
| `tests/test_mail_dispatch_windows.py`: mediodía en NY y Chicago, cambios de horario del 08-03 y del 01-11-2026, textos, hora máxima, tipos habilitados, todo apagado por defecto | **13/13 PASS** |
| Comando del cron en un proceso aparte (`MODE=TEST`) | PASS: código 0 y línea `MAIL DISPATCH` |
| Navegador de correo (11 escenarios) | **11/11 PASS** |
| `alembic heads` | `0024_activity_email_delivery (head)`, uno |
| Comando en local contra la copia de DigitalOcean (apagado) | `enabled=False dry_run=True checked=0`, código 0 |
| Regresión completa | **1.499 recogidos, 1 FAIL preexistente** |

## 5. Expected → Implemented → Evidence → Gap → Impact

| CR | Implementado | Evidencia | Brecha / impacto |
|---|---|---|---|
| CR-01 | Inventario y decisión del programador | Sección 1 | La App Spec real de DigitalOcean no se vio: **UNVERIFIED** |
| CR-02 | Job `SCHEDULED` cada 15 min, `--once` | App Spec versionada, comando probado | **No instalado; sin capturas de invocaciones**: lo hace CER (runbook §3) |
| CR-03 | Cuatro tipos con vencimiento y plantillas guardadas; T0 separado | Tests de ventanas y de cron/botón | — |
| CR-04 | 12:00 locales, zonas y cambio de horario | Tests unitarios de ventanas | **DP-TIMEZONE pendiente** |
| CR-05 | Fin de jornada +20; reapertura aplaza; End Work sin cambios | `test_fin_de_jornada…` (+19 no, +21 sí, reapertura) | Precisión real de ±1 min: depende del programador interno; **no medida en DigitalOcean** |
| CR-06 | Estratégico de mediodía por persona autorizada, sin resumen semanal | `test_estrategicos…` | — |
| CR-07 | Cierre completo o hora máxima; un Team Weekly Summary | `test_estrategicos…` | **DP-CUTOFF y DP-TEAM pendientes** |
| CR-08 | Sin actividad → omitido con motivo; destinatario no habilitado o inactivo → no se envía | `test_sin_actividad…`, `test_send_now_envia…` | — |
| CR-09 | Programador, cron y botón sin duplicados | `test_cron_y_boton_no_duplican`, `test_doble_clic…` | Dos réplicas reales: misma clave y bloqueo de PostgreSQL; no probado con dos procesos (LIKELY suficiente) |
| CR-10 | Fallos de credenciales, red, tiempo e incierto; recuperación de reserva caída; reintentos | `test_fallo…`, `test_tiempo_agotado…`, `test_una_reserva_caducada…` | — |
| CR-11 | Reloj inyectado (`ahora`), base real, multi-tenant, permisos, cambio de horario, medianoche | Tests de integración y unitarios | Medianoche: el cierre evalúa hoy y ayer; no hay un test específico de jornada que cruza la medianoche (**GAP menor**) |
| CR-12 | Commits, migración, runbook | Este reporte | **GO del PO y recepción real por tipo: PENDING** |

## 6. Bloqueos y siguiente paso
- **Correo saliente:** el administrador de Microsoft 365 debe dar SMTP.SendAsApp, registrar el service principal y el permiso sobre el buzón, y activar Authenticated SMTP. Después, Verify en `healthy`.
- **Instalar el job** (runbook §3) con la automatización **apagada**. Comprobar dos invocaciones en Activity › Jobs.
- **Decisiones del PO:** DP-TIMEZONE, DP-WEEK, DP-CUTOFF, DP-TEAM, DP-NOTES y DP-RECOVERY. Después, el GO por fases: ensayo → un tipo y pocas personas → ampliar.

## 7. Regresión completa y Git
`uv run pytest tests --ignore=tests/e2e`: **1.499 recogidos, 1 FAIL**, exit 1, 1.486 s. Los otros 1.498 pasaron u omitieron; el desglose no quedó capturado.
- **Único fallo:** `test_provisioning_alignment::…twelve_and_two_capabilities`, **preexistente desde RTE09** (espera 12 capacidades para `route_admin` y hay 16). Sin relación con este cambio.
- **Git:** rama `feature/mail-cp4-delivery`, desde `dev` `cfa4511`, migración `0024_activity_email_delivery`. **Un solo MR para CP4-01 y CP4-02**, porque comparten servicio y ledger. Sin fusionar.

## 8. Esfuerzo
Medido con `git diff --stat` de los dos checkpoints: 22 archivos, +2.590 líneas.

| Tarea | Volumen | Horas-agente |
|---|---|---|
| Generador real, despacho, ledger, migración, disparadores (backend) | ~1.250 LoC, 150 LoC/h | 8,3 |
| App Spec, runbook y documentación | ~125 líneas | 1,5 |
| Tests de integración y unitarios | ~480 LoC, 120 LoC/h | 4,0 |
| **Total CP4-01** | | **≈14** (CP4-01 + CP4-02 ≈ **25**) |
| Lo que falta: instalar el job, encender por fases y la prueba real | operación CER + ~2 h-agente de soporte | **+50 % por despliegue y navegador = ~3** |
