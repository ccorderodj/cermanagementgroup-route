# CER Route — Generate report: un mando puede pedir su propio reporte

**Fecha:** 2026-10-19 · **Rama:** `fix/report-self-target` → `dev` · **Entorno de la evidencia:** local

## Qué pasaba
En Activity Emails › plantilla › **Generate report**, el desplegable «Manager» / «Person» reutilizaba la lista de la pestaña de destinatarios. Esa lista solo incluye la **rama** de un mando, y la rama nunca le incluye a él mismo.

Diagnóstico sobre la base local (copia de DO, solo lecturas):

| Quién | Lista antes | Efecto |
|---|---|---|
| Superadmin | CEO y COO | Generaba bien. Lo que tenía bloqueado era *Send now*, porque `MAIL_REAL_SEND_TYPES` está vacío (apagado a propósito) |
| CEO | Solo el COO | No podía pedir su propio reporte |
| COO | Vacía | No podía pedir el suyo |

Causa (CONFIRMED): el servidor sí permitía pedir el propio reporte (`_objetivo` del router), pero la interfaz nunca ofrecía esa opción.

## Qué cambia
- Las listas `GET /api/activity-emails/recipients` y `/strategic-recipients` aceptan `include_self=true`. Solo lo usa el diálogo **Generate report**: añade a quien llama a su rama.
- La pestaña de destinatarios **no cambia**: un mando sigue sin poder activarse sus propios correos.
- Incluirse no amplía nada más. El COO sigue sin ver al CEO (404) ni ramas ajenas.

**Archivos:**
- `app/routers_api/activityemails/schemas.py`: el parámetro.
- `app/routers_api/activityemails/service.py`: `_alcance`, compartido por las dos listas.
- `app/routers_api/activityemails/router.py`.
- `entities/RouteActivityEmails/.../activityEmailsService.ts`: `includeSelf`.
- `features/RouteActivityEmails/ui/GenerateReportDialog.tsx`.
- `docs/MAIL_DISPATCH_RUNBOOK.md`.
- Tests: uno de integración y uno E2E.

## Cómo se comprobó (local)
| Prueba | Resultado |
|---|---|
| `import app.main` | OK |
| Integración, correos de actividad (3 archivos) | 52/52 PASS |
| `npm run check` | exit 0 (antes, un fallo propio por fines de línea CRLF; corregido) |
| `npm run build:prod` | exit 0 |
| E2E Generate report (Edge) | 4/4 PASS, incluido «el CEO genera su propio reporte» |
| Regresión completa (6 procesos, 1 h 17 min) | 1705 PASS · 6 FAIL · 15 skipped · ninguno de los 6 es de este cambio |

**Los 6 fallos de la regresión. Ninguno es de este cambio:**
- `test_provisioning_alignment`: ya fallaba antes; espera 12 capacidades de route_admin y hay 16.
- 4 tests de `test_rte06_recovery_accuracy_browser.py` y 1 de `test_rte06_offline_durability_browser.py` (ubicación sin conexión):
  - repetidos aislados, sin paralelo: los mismos 5 fallan;
  - `test_g5_candidato_malo_y_luego_bueno` **también falla en `dev` sin este cambio** (CONFIRMED que es anterior);
  - la causa raíz está sin investigar (UNVERIFIED). Hallazgo aparte, fuera del alcance de este MR.

## Lo que necesito de ti
| Qué | Por qué |
|---|---|
| Asignar al COO (y a quien deba usarlo) `route.activityemails.manage` y `route.activityemails.preview` en DO | Sin `manage` no entra a la pantalla; sin `preview` no ve el botón. Son a demanda |
| Revisar y fusionar el MR | No se fusiona desde aquí |

## Pendientes operativos
- No hay migración ni converge en este cambio.
- El envío real sigue apagado (`MAIL_REAL_SEND_TYPES` vacío) hasta las decisiones de producto.

## Esfuerzo
| Tarea | Estado | Volumen | Horas-agente |
|---|---|---|---|
| Diagnóstico | Hecho | consultas locales | 0,3 h |
| Backend + frontend | Hecho | ~60 LoC | 0,4 h |
| Tests (integración + E2E) | Hecho | ~55 LoC | 0,6 h |
| Restante | — | — | 0 h |
