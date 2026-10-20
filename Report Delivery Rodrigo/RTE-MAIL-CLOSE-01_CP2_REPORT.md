# RTE-MAIL-CLOSE-01 · CP2 — Estado operativo y Delivery History

**Fecha:** 2026-10-20 · **Rama:** `feature/rte-mail-close-01` · **Commit:** `7c392fe` · **Entorno de la evidencia:** local
**Estado:** IMPLEMENTED + VALIDATED en local · NOT DEPLOYED

## Expected → Implemented → Evidence → Gap

| Expected | Implemented | Evidence (local) | Gap / Impact |
|---|---|---|---|
| Sustituir el aviso fijo «automatización pendiente» por estado **leído del backend** | `GET /api/activity-emails/status` y el aviso **Delivery status**: proveedor (Verify y fecha), automático Off / Dry run / On, tipos con envío real y **última pasada vista** de cada reloj («not observed yet» si nunca corrió). La nota «Accepted ≠ delivered» se muestra siempre | `test_estado_leido_del_servidor` PASS (403 sin `manage`; sin secretos) · E2E escritorio y móvil PASS | El toast de guardar plantilla también decía «pendiente de habilitación»; corregido |
| Saber si el job corrió sin leer logs | Cada pasada (también apagada) deja su latido por reloj en `activity_email_dispatch_run` (migración **0027**): inicio, fin, resultado y contadores. Sin datos de personas | Mismo test: tras una pasada `reconcile`, el estado la muestra | Es la **última** pasada, no un historial de ejecuciones (eso está en los logs de DO) |
| Delivery History: fecha, tipo, destinatario, zona/corte, disparador, intento, estado, motivo, próximo reintento; filtros; sin contenido | `GET /api/activity-emails/history` y la pestaña **Delivery history**: entregas con sus **reenvíos**; retraso respecto al vencimiento en los automáticos; filtros por fechas, correo y disparador (Scheduler, DigitalOcean job, Send now, Resend); acotado como el resto (rama + uno mismo) | `test_historial_con_reenvios_filtros_y_sin_contenido`, `test_historial_acotado_a_la_rama` PASS · capturas `var/screenshots/mail-close/escritorio-historial.png`, `movil-historial.png` (sin scroll horizontal) | Las pruebas con datos ficticios (`mail_test_send`) no entran: no son envíos reales. Siguen en Platform |
| Nunca perder un envío en silencio | Sin zona → fila **pendiente** `configuration_required`; sale en cuanto se fija, en la misma fila. Vencido fuera de la ventana → `recovery_window_expired`, visible y enviable a mano | `test_sin_zona_queda_pendiente_y_a_la_vista` (salió 1 h tarde y se ve `delay_seconds=3600`), `test_fuera_de_la_ventana_queda_registrado…` PASS | Ventana de recuperación sin cambios (2 h) |
| Conservar Generate report, Send now, Resend (permiso separado), cuotas e idempotencia | Sin cambios de comportamiento; los textos de estado se comparten (`lib/labels.ts`) | E2E de Generate report 5/5 y tests de reenvío PASS | — |
| Permisos | Estado e historial exigen `route.activityemails.manage`. Ninguna capacidad nueva | `test_permission_catalog`, `test_public_surface` PASS | — |

## Fallos durante el trabajo (CONFIRMED, corregidos)
- **Migración 0027:** el identificador de revisión medía 33 caracteres y la tabla de Alembic admite 32. Se acortó a `0027_activity_email_obs`; no se aplicó nada a medias.
- **E2E existente:** fallaba porque la tabla de latidos no se vaciaba entre tests (no cuelga de ninguna compañía). Se añadió a la limpieza de tests.

## Migración
`0027_activity_email_obs`: tabla nueva y la columna `activity_email_delivery.time_zone`. Las filas anteriores quedan con la zona vacía; no se deduce. Up → down → up OK en local · 1 head.

## Comandos
- Lote de correos, permisos y cableado: **199 passed**, exit 0.
- E2E de correos (Edge): **9 passed** (incluye `test_mail_close_browser.py`).
- `npm run check`: exit 0. `npm run build:prod`: exit 0.
