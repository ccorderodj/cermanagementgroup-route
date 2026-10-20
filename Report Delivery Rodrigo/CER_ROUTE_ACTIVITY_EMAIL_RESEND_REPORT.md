# CER Route — Reenviar un correo de actividad que ya salió

**Fecha:** 2026-10-19 · **Rama:** `feature/activity-email-resend` → `dev` · **Entorno de la evidencia:** local

## Qué pasaba
**Send now** solo recupera un correo que tocaba y **no** salió. Una vez aceptado por el proveedor, el botón queda desactivado («Already accepted… Resending is not available»). No había forma de volver a mandar un reporte que no llegó o que hacía falta repetir.

## Qué cambia
- **Botón Resend** en Activity Emails › plantilla › Generate report. Aparece cuando el correo de ese día ya fue aceptado por el proveedor o quedó con resultado incierto.
- **Lo autoriza solo un permiso nuevo**, `route.activityemails.resend`, a demanda (nadie lo tiene por defecto). Tener `send` no basta.
- **Qué no se mira:** el interruptor de la persona en Recipients ni la hora de vencimiento.
- **Qué se sigue respetando:**
  - el interruptor de emergencia por tipo (`MAIL_REAL_SEND_TYPES`);
  - que el destinatario esté activo y tenga un correo válido;
  - el límite de 20 envíos a mano por hora y persona;
  - el destinatario configurado, nunca una dirección escrita.
- **Un doble clic no manda dos.** Cada reenvío se numera (#1, #2…) y la base impide dos con el mismo número.
- **Historial y auditoría:** el historial del diálogo muestra cada reenvío, y cada uno queda en `audit_event`. La entrega original sigue siendo una sola por persona, tipo y día.

**Archivos:**
- Backend:
  - `delivery.py`: `reenviar`, y `_mandar`, compartido con Send now;
  - `models.py`: `ActivityEmailResend`;
  - `router.py`: `POST /api/activity-emails/reports/resend`;
  - `schemas.py`;
  - `catalog.py`: la capacidad nueva.
- Migración `0025_activity_email_resend`: tabla nueva y restricciones.
- Frontend: tipos y servicio de la entidad, y `GenerateReportDialog.tsx`.
- Documentación: `docs/MAIL_DISPATCH_RUNBOOK.md` y `docs/ARCHITECTURE.md`.
- Tests: 5 de integración, una ampliación de un test existente y 1 E2E.

## Cómo se comprobó (local)
| Prueba | Resultado |
|---|---|
| `import app.main` | OK |
| Migración 0025: subida, bajada y subida | OK · un solo head (`0025_activity_email_resend`) |
| Integración de envíos y reenvíos + catálogo de permisos + superficie pública | 46/46 PASS |
| La base rechaza un reenvío duplicado, con número 0 o con un estado inventado | PASS (dentro de los 46) |
| `npm run check` y `npm run build:prod` | exit 0 |
| E2E de Generate report (Edge) | 5/5 PASS. Primero falló uno existente por un error mío en la condición del mensaje; corregido |
| Regresión completa (6 procesos, 1 h 04 min) | 1711 PASS · 6 FAIL · 15 skipped. Los 6 son los que ya fallaban en `dev`: `test_provisioning_alignment` y 5 E2E de ubicación sin conexión (RTE-06). Ninguno nuevo |

## Lo que necesito de ti
| Qué | Por qué |
|---|---|
| Revisar y fusionar el MR | No se fusiona desde aquí |
| Asignar `route.activityemails.resend` a los roles que deban reenviar | Es a demanda: nadie lo tiene por defecto |

## Pendientes operativos
- Al desplegar, el job `migrate` aplica la migración 0025 y `converge` crea la capacidad nueva. No hay que ejecutar nada a mano.
- Base local: además de este cambio, tenía pendiente la migración 0024, que se aplicó junto con la 0025.

## Esfuerzo
| Tarea | Estado | Volumen | Horas-agente |
|---|---|---|---|
| Backend + migración | Hecho | ~230 LoC | 1,3 h |
| Frontend | Hecho | ~110 LoC | 0,6 h |
| Tests (integración + E2E) | Hecho | ~150 LoC | 0,9 h |
| Restante | — | — | 0 h |
