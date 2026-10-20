# RTE-MAIL-CLOSE-01 · CP3 — DigitalOcean y GO operativo controlado

**Fecha:** 2026-10-20 · **Rama:** `feature/rte-mail-close-01` · **Commit:** `1e7e4c8`
**Estado: BLOCKED.** No hay acceso a DigitalOcean desde aquí. Lo accesible está hecho; **no se declara automatización operativa**.

## Expected → Implemented → Evidence → Gap

| Expected | Implemented | Evidence | Gap / Impact |
|---|---|---|---|
| Auditar la App Spec real y adoptar la **menor configuración suficiente**, sin duplicar | Conciliada con la spec real que pegó CER. Queda: `migrate` (alembic + `converge`) y **un** job `route-mail-reconcile` `*/15` UTC. Se **descarta** la propuesta anterior de tres jobs: ejecutaban la misma pasada sobre la misma clave, sin añadir precisión ni cobertura. La precisión la da el programador interno (cada minuto) | `_cer_delivery/APP_SPEC_cerroute-dev.yaml` (secretos con marcador) | Ninguno. **No aplicar** la propuesta de tres jobs |
| Scheduler + job comparten servicio, reglas, ledger y clave | Ya era así. CP2 añade el latido por reloj para verlo en pantalla | Tests de cron + botón sin duplicados PASS (local) | — |
| Dos ejecuciones reales del job | **Local:** 2 ejecuciones de `python -m app.routers_api.activityemails.jobs --once`, en modo ensayo, contra la copia local | exit 0 las dos; `checked=24 would_send=0 config_required=3 expired=5`; latido registrado; ledger sin escrituras | **BLOCKED en DO:** hacen falta las invocaciones del job en Activity › Jobs |
| Migraciones aplicadas | 0026 y 0027 se aplican en el `migrate` del despliegue | Up/down/up OK en local | **BLOCKED en DO:** comprobar el log de `migrate` |
| Dry-run controlado, piloto, recepción T1–T4, ciclo mediodía + cierre (con T2) | Procedimiento exacto en el runbook (sección 5) | — | **BLOCKED:** necesita despliegue, la zona de la compañía, el GO del PO y buzones de prueba |
| Kill switch y rollback | `MAIL_AUTOMATION_ENABLED=false` lo para en la pasada siguiente. Las migraciones se pueden bajar | Test de automatización apagada / dry-run sin escrituras PASS | — |

## Procedimiento para desbloquear (en orden)
1. **Fusionar el MR y esperar el despliegue de `dev`.** En el log de `migrate` deben verse `0026_company_time_zone`, `0027_activity_email_obs` y `CONFIGURATION CONVERGE`.
2. **Company Profile › Operational time zone:** la zona de `cerroute` (decisión de CER). Sin ella, los destinatarios sin zona propia (Liber, superadmin) quedan en `configuration_required`.
3. **Activity Emails:** el aviso debe decir «Mail provider: Verified» y mostrar pasadas de **In-app scheduler** (≤ 1–2 min) y **DigitalOcean job** (≤ 15 min). Captura.
4. **Ensayo, un día:** `MAIL_AUTOMATION_ENABLED=true`, `MAIL_AUTOMATION_DRY_RUN=true`. Revisar en los logs de las líneas `MAIL DISPATCH` los contadores `would_send`, `config_required` y `expired`.
5. **Piloto:** `MAIL_AUTOMATION_DRY_RUN=false` con el interruptor de **1–2 personas** por tipo en Recipients (`MAIL_REAL_SEND_TYPES` ya lista los cuatro). Un día completo: 12:00 (T1, T3), End Work + 20 (T2) y 19:00 (T4). Por cada correo: fila en Delivery history **y** recepción comprobada en el buzón.
6. **Parar si algo va mal:** `MAIL_AUTOMATION_ENABLED=false`.

## Estado real hoy (según lo que pegó CER)
- `MAIL_AUTOMATION_ENABLED=false`: **no sale nada automático**.
- `MAIL_REAL_SEND_TYPES` con los cuatro tipos: Send now y Resend funcionan a mano.
- Un solo reconciliador instalado.

**Done** exige evidencia de ejecución automática en DigitalOcean y contenido correcto recibido. **Todavía no existe.**

## Regresión completa (local, estado final de la rama)
`uv run pytest tests -n 6` → **1730 passed · 6 failed · 15 skipped** (1 h 02 min). Los 6 son los que ya fallaban en `dev` antes de esta entrega:
- `test_provisioning_alignment`: espera 12 capacidades de route_admin y hay 16.
- 5 E2E de ubicación sin conexión (RTE-06).

Ningún fallo nuevo.
