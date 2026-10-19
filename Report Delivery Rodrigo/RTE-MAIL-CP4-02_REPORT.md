# RTE-MAIL-CP4-02 — Reportes a demanda y envío manual de respaldo

**Reporte** · 19 de octubre de 2026
**Instrucción:** `_cer_delivery/RTE-MAIL-CP4-02_ON_DEMAND_REPORT_FALLBACK_V1_0.md`
**Status: PARTIAL.** Implementado y validado en local (CP4-02A y CP4-02B completos, CP4-02C parcial).

**No se declara DONE**, por tres motivos:
- **no hay recepción real** en un buzón: el proveedor de correo todavía no funciona (Exchange rechaza el inicio de sesión);
- **el envío real está apagado por diseño** hasta el GO del PO;
- **siguen abiertas** DP-TIMEZONE, DP-WEEK, DP-CUTOFF, DP-TEAM, DP-NOTES y DP-RECOVERY.

## 1. Checkpoints

| CP | Estado | Evidencia |
|---|---|---|
| CP4-02A: botones y vista previa real con permisos y tenant | **Completed** | Sección 4, tests de integración y navegador |
| CP4-02B: envío manual seguro (servicio común, elegibilidad, idempotencia, historial, confirmación, errores, reintentos) | **Completed** | Sección 4 |
| CP4-02C: pruebas integradas, despliegue y recepción real | **Partial** | Carrera manual/cron, doble clic y regresión **probados en local**. **Despliegue y recepción real: BLOCKED** (proveedor y GO) |

## 2. Lo construido
- **Pantalla:** en **Activity Emails**, en cada plantilla y junto a *Preview* y *Send test*, que no cambian, un botón **Generate report**. Abre un diálogo con:
  - selección del destinatario (persona o mando, de las listas de Recipients ya acotadas al alcance) y del día operativo;
  - **Generate report:** vista previa con **datos reales y la plantilla guardada**. Muestra destinatario y correo enmascarado (`s***r@…`), zona horaria, corte («Data until»), vencimiento, momento de generación, **Parcial o Final**, personas cubiertas, actividades y el motivo si no hay correo;
  - **Send now:** deshabilitado si no se puede, **con el motivo**. Antes de enviar hay confirmación (quién, qué tipo, día, ventana y aviso de que el envío programado no lo repetirá) y un motivo opcional, que queda auditado;
  - el resultado y el **historial del día**, con estados honestos: «Accepted by the mail provider (delivery not confirmed)», «Uncertain outcome — needs reconciliation»…
- **API** (privada; T0-T4 y `test-send` sin cambios):

| Endpoint | Permiso | Qué hace |
|---|---|---|
| `POST /api/activity-emails/reports/preview` `{report_type, recipient_user_id, operational_date}` | `route.activityemails.preview` | Vista previa real. **No escribe ni envía** |
| `POST /api/activity-emails/reports/send` (lo mismo + `reason?`) | `route.activityemails.send` | Reevalúa todo y envía al destinatario configurado, o responde 409 con un código |
| `GET /api/activity-emails/reports/deliveries?report_type&recipient_user_id&operational_date` | `route.activityemails.preview` | Historial sin contenido, acotado al alcance |

- **Permisos (OD-10):** dos capacidades nuevas **a demanda**, que ninguna plantilla de rol concede: `route.activityemails.preview` (ver datos reales) y `route.activityemails.send` (enviar). Son distintas entre sí y distintas de `manage` (configurar). **Ver no autoriza a enviar.**
- **Alcance:**
  - el destinatario **debe pertenecer a la compañía** (404 si es de otro tenant) y estar en la delegación de quien pide;
  - un mando puede pedir **su propio** reporte;
  - los estratégicos usan el alcance del **mando**: el CEO incluye Sales y el COO no.
- **Servicio común con CP4-01:** `activityemails/real_reports.py` (generador) y `activityemails/delivery.py` (evaluar, reservar, entregar, omitir, historial). Ver el reporte de CP4-01.

## 3. Reglas aplicadas (§6, §7)
- **Mediodía:** corte fijo a las **12:00 locales** del día elegido aunque se genere más tarde. Antes de las 12:00, «Partial» y **no se envía**.
- **Fin de jornada motivacional:** solo con **todas** las jornadas del día cerradas; vence a los 20 min del último cierre. Si se reabre, vuelve a ser parcial.
- **Estratégico de cierre:** equipo completo cerrado, o la hora máxima `MAIL_STRATEGIC_CUTOFF` (vacía = no elegida). Si no, «Partial» y no se envía.
- **Sin actividad no hay motivacional** (`no_activity`). Los motivacionales no llevan notas, rutas, clientes, millas ni combustible. Los estratégicos **nunca** llevan notas reales: «Detalle no incluido en el correo».
- **El botón recupera, no adelanta:** antes del vencimiento, `not_due_yet`.
- **Ya aceptado:** `already_sent` y el botón deshabilitado. **No hay reenvío**: necesita aprobación del PO (§7).
- **Fallo reintentable:** «Send now» reintenta **sobre el mismo registro** (intento 2…), hasta 5.
- **Incierto** (tiempo agotado con el mensaje en vuelo, o reserva caducada): `needs_reconciliation` y no se reenvía.
- **Límite:** 20 envíos manuales por persona y hora (429). Las pruebas T0-T4 siguen con su presupuesto propio y **no cuentan** como envíos reales.
- **Auditoría:** cada resultado deja un `audit_event` (`activity_email_delivery`) con tipo, destinatario, día, estado, motivo y origen; nunca el cuerpo. El ledger guarda quién lo pidió y su motivo.

## 4. Pruebas (local, base de tests)

| Lote | Comando | Resultado |
|---|---|---|
| Integración del envío real (compartida con CP4-01) | `uv run pytest tests/integration/test_activity_email_delivery.py` | **19/19 PASS** |
| Ventanas, textos y valores por defecto | `uv run pytest tests/test_mail_dispatch_windows.py` | **13/13 PASS**: mediodía en dos zonas y en los dos cambios de horario de 2026 |
| Catálogo de permisos y superficie pública | `uv run pytest tests/test_permission_catalog.py tests/test_public_surface.py` | **PASS** (junto con el anterior, 32/32) |
| Navegador: generar y enviar con confirmación (escritorio); apagado por defecto con su motivo (móvil); sin permiso de envío no hay botón | `uv run pytest tests/e2e/test_activity_email_reports_browser.py -n 0` | **3/3 PASS** |
| Navegador: Activity Emails, T0 y pruebas (regresión) | `… test_activity_emails_browser.py test_mail_provider_test_browser.py -n 0` | **8/8 PASS** (11/11 en total) |
| Frontend | `npm run check` / `npm run build:prod` | exit 0 / exit 0 |
| Regresión completa | `uv run pytest tests --ignore=tests/e2e` | **1.499 recogidos, 1 FAIL preexistente** |

**Cubierto en los 19 tests:**
- **Permisos y alcance:** permisos separados (403); otro tenant (404); campo extra (422); un COO fuera de su rama (404) y su propio reporte (200).
- **Ventanas y contenido:** corte a las 12:00 con datos reales; actividad posterior al mediodía que no cuenta; vista parcial antes de las 12:00; fin de jornada a +19 min (no) y +21 min (sí), y aplazado al reabrir; estratégicos con cobertura 4 y sin notas.
- **Envío:**
  - apagado por defecto;
  - envío único con historial y auditoría;
  - doble clic (3 simultáneos → 1 envío);
  - fallo del proveedor y reintento sobre el mismo registro;
  - tiempo agotado → incierto, sin reenvío.
- **Junto con el cron:** cron y botón sin duplicados; ensayo y automatización apagada sin escribir nada; omisión por falta de actividad; ventana de recuperación; reserva caducada → incierta; comando del cron en un proceso aparte.

**Hallazgos durante el desarrollo (CONFIRMED, corregidos antes de entregar):**
- **Otro tenant devolvía 200.** Un administrador sin rol de mando podía pedir la vista previa de un usuario de otro tenant y veía su nombre: la delegación no acota a un actor de tenant. Ahora se exige pertenencia a la compañía (404).
- **«Send now» seguía activo después de enviar** con la vista previa antigua. Ahora la vista se recarga y dice «Already accepted…».
- **Ajustes de tests:**
  - el producto no permite cerrar una jornada con una parada abierta, así que el test de «sin actividad» usa un viaje a casa;
  - el comando del cron se prueba en un proceso aparte;
  - la consulta de preparación necesitaba convertir el tipo de fecha.

## 5. Expected → Implemented → Evidence → Gap → Impact

| OD | Implementado | Evidencia | Brecha / impacto |
|---|---|---|---|
| OD-01 | Generate report / Send now en Activity Emails; T0-T4 sin cambios | E2E (11/11) | — |
| OD-02 | Vista previa real con la plantilla guardada, ventana y destinatario válido | `test_mediodia_con_corte_fijo_a_las_12`, E2E | — |
| OD-03 | Motivacional sin notas, rutas, clientes ni millas | Mismo test (texto prohibido ausente) | — |
| OD-04 | Corte a las 12:00 locales; antes, solo parcial | `test_antes_del_mediodia_solo_vista_parcial` | La zona sale de la regla de Today y Reports; **DP-TIMEZONE pendiente** |
| OD-05 | Cierre solo con jornadas cerradas y actividades; reapertura → parcial | `test_fin_de_jornada…`, `test_sin_actividad…` | — |
| OD-06 | Estratégico con el alcance del mando; notas retenidas; sin datos de otro tenant | `test_estrategicos…`, `test_un_coo…`, `test_permisos…` | — |
| OD-07 | Cierre por persona y un solo Team Weekly Summary | `test_estrategicos…` (`count == 1`) | Semana desde el lunes: **DP-WEEK pendiente** |
| OD-08 | El botón recupera un vencido; el cron después no repite; la vista previa no reserva | `test_cron_y_boton_no_duplican`, sin filas tras la vista previa | — |
| OD-09 | Error, proveedor, reintento, aceptado e incierto mostrados con honestidad; reenvío bloqueado | `test_fallo…`, `test_tiempo_agotado…`, E2E | — |
| OD-10 | `manage` / `preview` / `send` separados, en backend y en pantalla | `test_permisos…`, E2E sin permiso | — |
| OD-11 | Auditoría sin contenido; doble clic, cron y manual, revocación (interruptor) entre vista y envío | `test_doble_clic…`, `test_send_now_envia…` (`recipient_not_enabled`) | Dos réplicas reales: la clave única y el bloqueo de fila son de PostgreSQL. Probado con peticiones simultáneas, **no con dos procesos web** (LIKELY suficiente) |
| OD-12 | Responsive, regresión, capturas, migración, reporte | E2E móvil, sección 7, `var/screenshots/activity-email-reports/` | **Recepción real: BLOCKED** |

## 6. Decisiones pendientes del PO
- **DP-TIMEZONE:** fuente de la zona (hoy: override del perfil o zona de la última jornada; el mando sin jornada usa la más frecuente de su equipo).
- **DP-WEEK:** inicio de semana (hoy, lunes, como Activity).
- **DP-CUTOFF:** hora máxima del estratégico de cierre (vacía).
- **DP-TEAM:** evidencia de cierre del equipo (hoy, todas sus jornadas del día cerradas).
- **DP-NOTES:** ninguna nota real sale.
- **DP-RECOVERY:** ventana de recuperación (hoy, 2 h, configurable).
- **Nuevo:** ¿se permite el **reenvío** de un correo ya aceptado (§7)? Hoy está bloqueado.
- **Nuevo:** si nadie del equipo trabajó, el estratégico de cierre **no se envía** y queda omitido con el motivo `no_team_activity`. Hay que confirmarlo.

## 7. Regresión completa y Git
`uv run pytest tests --ignore=tests/e2e`: **1.499 recogidos, 1 FAIL**, exit 1, 1.486 s. Los otros 1.498 pasaron u omitieron; el desglose no quedó capturado.
- **Único fallo:** `test_provisioning_alignment::…twelve_and_two_capabilities`, **preexistente desde RTE09** (espera 12 capacidades para `route_admin` y hay 16). Sin relación con este cambio.
- **Git:** rama `feature/mail-cp4-delivery`, desde `dev` `cfa4511`, migración `0024_activity_email_delivery`. **Un solo MR para CP4-01 y CP4-02**, porque comparten servicio y ledger. Sin fusionar.

## 8. Esfuerzo
Esfuerzo de CP4-02. Medido con `git diff --stat`; el servicio común se cuenta en CP4-01.

| Tarea | Volumen | Horas-agente |
|---|---|---|
| API, permisos y alcance | ~200 LoC, 175 LoC/h | 1,2 |
| Pantalla: diálogo, servicios y tipos | ~450 LoC, 60 LoC/h | 7,5 |
| Tests de navegador | ~140 LoC, 60 LoC/h | 2,3 |
| **Total CP4-02** | | **≈11** |
