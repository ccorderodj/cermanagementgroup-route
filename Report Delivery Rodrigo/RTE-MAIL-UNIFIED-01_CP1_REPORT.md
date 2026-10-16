# RTE-MAIL-UNIFIED-01 · CP1: conciliación y endurecimiento de las pruebas de correo

**Reporte técnico CP1** · 16 de octubre de 2026
**Instrucción:** `_cer_delivery/RTE-MAIL-UNIFIED-01_TEST_SEND_AND_STRATEGIC_REPORTS_V1_1.md`
**Status CP1: COMPLETED WITH PENDING VALIDATION.** Implementado y validado en local.
- Pendiente: despliegue y recepción real en un buzón. Esto último está **BLOCKED EXTERNAL CONFIGURATION**: no hay proveedor configurado.
- **CP2 y CP3 no se han empezado**, como pide §12. Esperan la revisión de este CP.

> **No se ha enviado ningún correo real.** Nada programado, nadie suscrito, sin notas reales.

## 1. Conciliación del punto de partida (AC-01)

| Elemento | Estado | Evidencia |
|---|---|---|
| RTE-MAIL-TEST-01 (T1/T2 Send test, `test-targets`, `MAIL_TEST_RECIPIENTS`) | **AS-BUILT/CONFIRMED en `dev`** | MR !103 fusionado (`ffe8f1f`). Esta rama sale de ahí |
| Platform › Integrations & Settings / Diagnostics | AS-BUILT | `IntegrationGuideSheet.tsx`, `diagnostics_router.py` |
| Activity Emails (2 plantillas, destinatarios, vista previa) | AS-BUILT | `app/routers_api/activityemails/` |
| Área «Mail» independiente | No existe y **no se crea** (§4) | — |
| Referencias `RTE-NOT-STR-01_…V1_1.md` y `RTE-MAIL-TEST-02_…V1_0.md` | **No están en el repositorio** | Se trabajó solo con esta instrucción, que dice ser la autoritativa |
| Despliegue en DigitalOcean de T1/T2 | **UNVERIFIED** | Desde aquí no se ve qué build está desplegado (§9.2, paso 1) |
| Proveedor configurado | **No**, en la copia local de DigitalOcean | Ver RTE-MAIL-TEST-01 §3 |

## 2. Qué cambia en CP1

### 2.1 Una sola política de pruebas: `app/core/email/politica_de_prueba.py`
La comparten T0 (proveedor) y T1/T2 (plantillas); antes cada camino tenía la suya.

| Regla | Antes | Ahora |
|---|---|---|
| Destino de T0 | **Cualquier dirección** (deuda de RTE-MAIL-TEST-01) | Solo el propio correo o `MAIL_TEST_RECIPIENTS`; si no, 403 |
| Campos extra en T0 (`cc`, `bcc`…) | **Se ignoraban en silencio** (lo detectó un test nuevo) | 422 (`extra="forbid"`) |
| Presupuesto | Solo T1/T2, contado en la auditoría; T0 sin límite | **Uno compartido:** 5 por persona cada 15 min, sumando T0 y T1/T2, en la tabla `mail_test_send` |
| Concurrencia | Se contaba y después se enviaba (carrera posible) | **Reserva antes de enviar**, bajo `pg_advisory_xact_lock` por persona: vale entre réplicas |
| Asunto de T0 | «… — test message» | `[TEST] CER Route — Email integration`. «[TEST]» exactamente una vez, también en plantillas que ya lo traigan |
| Marcado | Solo T1/T2 | Los dos: banner «CORREO DE PRUEBA — datos ficticios» y cabecera `X-CER-Route-Test` |
| Respaldo en T0 | Ya usaba el proveedor elegido | Se mantiene y se prueba: si el elegido no está configurado, `not_configured` (409), aunque el de respaldo sí lo esté. **No consume presupuesto** |
| Resultado de T0 | `{"sent": true}` | `outcome` + `backend` real + `delivered_confirmed: false` |
| Fallos | T0 devolvía el texto del proveedor | Mensaje fijo; ni la respuesta ni la auditoría llevan el texto del proveedor |

**Resultados posibles:** `accepted_by_provider`, `not_sent_development_backend`, `captured_by_test_backend`, `not_configured`, `failed_auth`, `failed_unreachable`. Denegaciones: 401, 403, 422 y 429. Ninguno es «entregado».

### 2.2 Interfaz
- **Platform › Outbound email, paso Verify:**
  - **Verify** (comprueba sin enviar) y **Send Test Email** quedan separados;
  - el destino se elige de la lista del servidor, **sin campo libre**;
  - el resultado muestra el backend real y que la entrega no está confirmada.
- **Activity Emails › Send test:** igual que antes, ahora con el backend real en el resultado.

### 2.3 Base de datos
**Migración `0022_mail_test_send`** (revisa `0021`). Un solo head.
- Columnas: `actor_user_id`, `company_id` (vacío en T0), `channel` (`provider` / `template`, con CHECK), `target`, `destination`, `outcome` (con CHECK), `backend`, `created_at`, `finished_at`.
- Índice `(actor_user_id, created_at)`.
- **No guarda** asunto, cuerpo ni texto del proveedor. No escribe filas.
- La bajada borra la tabla; la auditoría queda.

### 2.4 API (cambios)

| Endpoint | Cambio |
|---|---|
| `GET /api/platform/integrations/{key}/test-targets` | **Nuevo** (solo administradores de plataforma): buzones permitidos y límite |
| `POST /api/platform/integrations/{key}/test-message` | Endurecido (sección 2.1); responde `{outcome, to, backend, delivered_confirmed}` |
| `POST /api/activity-emails/templates/{tipo}/test-send` | Usa la política común; añade `backend` a la respuesta |

**Sin permisos nuevos:** T0 sigue con `require_platform_admin` y T1/T2 con `route.activityemails.manage`.

## 3. Criterios de aceptación en el alcance de CP1

| AC | Esperado → Implementado → Evidencia | Brecha / impacto |
|---|---|---|
| AC-01 | Superficies y rama confirmadas, sin módulo Mail duplicado → sección 1 | — |
| AC-02 | Verify y Send Test Email separados y seguros; T0 con buzón aprobado y límite → sección 2 → `test_t0_*` (5 tests), E2E T0 escritorio y móvil | — |
| AC-03 | T1/T2 intactos con texto guardado y reglas comunes → `test_activity_email_test_send` (8), `test_test_una_sola_vez_en_el_asunto`, E2E Activity Emails (4) | — |
| AC-09 (parcial) | Destinos aprobados, 401/403/422/429, presupuesto compartido y concurrente, auditoría segura, sin tocar estado → `test_presupuesto_compartido…`, `test_presupuesto_con_peticiones_simultaneas` (9 simultáneas → exactamente 5 × 200 y 4 × 429) | La concurrencia se probó contra un único servidor; el candado es de PostgreSQL, así que también vale entre réplicas (LIKELY, no probado con dos procesos) |
| AC-10 (parcial) | La interfaz distingue aceptado, capturado y no configurado | **Recepción real: BLOCKED EXTERNAL CONFIGURATION** |
| AC-04 a AC-08, AC-07A, AC-11 | CP2 / CP3 | **NOT STARTED**, por diseño (§12) |

## 4. Pruebas ejecutadas (local, base de tests)

| Lote | Comando | Resultado |
|---|---|---|
| Política, T0, T1/T2, diagnósticos de plataforma, cabecera, superficie pública, catálogo | `uv run pytest tests/integration/test_mail_test_policy.py tests/integration/test_activity_email_test_send.py tests/integration/test_platform_diagnostics.py tests/test_email_test_header.py tests/test_public_surface.py tests/test_permission_catalog.py` | **56/56 PASS** (primera ejecución: 1 FAIL, sección 5) |
| Navegador: T0 (escritorio y móvil) + Activity Emails | `uv run pytest tests/e2e/test_mail_provider_test_browser.py tests/e2e/test_activity_emails_browser.py -n 0` | **6/6 PASS** (fallos previos del localizador del test, sección 5) |
| Migraciones | `alembic heads` | `0022_mail_test_send (head)`, uno |
| Frontend | `npm run check` / `npm run build:prod` | exit 0 / exit 0 |
| Regresión completa | `uv run pytest tests --ignore=tests/e2e` | **1.432 recogidos, 1 FAIL preexistente**, exit 1, 1.456 s |

## 5. Hallazgos durante la ejecución

| Qué | Causa | Estado |
|---|---|---|
| **T0 aceptaba `cc` y lo ignoraba** | **CONFIRMED:** `TestMessageWrite` no prohibía campos extra | Corregido: 422 |
| E2E T0: no encontraba la tarjeta ni el botón Verify | **CONFIRMED:** localizadores ambiguos del test (cinco botones «Set up»; «4 Verify» en la barra de pasos) | Test corregido (`#integration-email`, `exact=True`) |
| Heredoc de bash roto al editar el panel | Herramienta | Edición aplicada con un script aparte; sin efecto en el producto |

## 6. Verificación real con correo (la hace CER; §9.2)
1. **Desplegar** esta rama una vez fusionada (migración 0022). Comprobar que en Outbound email, paso Verify, sale «Send Test Email» con la lista de buzones.
2. **Configurar el proveedor** en Platform › Integrations & Settings, con las claves **solo ahí**.
3. **Verify:** debe dar `healthy`.
4. **Opcional:** `MAIL_TEST_RECIPIENTS` con el buzón de prueba de CER.
5. **T0:** Send Test Email → «Accepted by m365_oauth…».
6. **T1 y T2:** Activity Emails → Send test en cada plantilla. Van 3 de las 5 pruebas permitidas cada 15 min.
7. **Mirar el buzón (y spam), guardar capturas** y comprobar SPF, DKIM y DMARC.
8. Hasta entonces, AC-10 queda **PENDING DELIVERY VALIDATION**.

## 7. Regresión completa y Git
`uv run pytest tests --ignore=tests/e2e`: **1.432 recogidos, 1 FAIL**, exit 1, 1.456 s. Los otros 1.431 pasaron u omitieron; el desglose no quedó capturado.
- **Único fallo: `test_provisioning_alignment::…twelve_and_two_capabilities`.** Preexistente desde RTE09 (`CONFIRMED`): espera 12 capacidades para `route_admin` y hay 16. No tiene relación con este cambio.
- El fallo de «archivo no versionado» del reporte anterior **no se repitió**: los archivos estaban añadidos a git antes de la ejecución.

Git: rama `feature/mail-u01-cp1`, desde `dev` `ffe8f1f`. Migración `0022_mail_test_send`.

## 8. Para la revisión de CP1 y el paso a CP2
**Decisiones que ya afectan a CP2** (no bloquean empezarlo, pero sí la certificación):
- DP-NOTES: qué notas pueden ir por correo.
- DP-WEEK: inicio de semana.
- DP-TIMEZONE: zona horaria de los reportes.
- DP-SCOPE: confirmar todos los descendientes autorizados, sin el trabajo propio del mando.

**Propuesta para CP2:** reutilizar Activity Emails, con las dos plantillas estratégicas en un grupo separado de la misma página.
- Interruptores de mandos en una tabla aparte, apagados por defecto.
- Un generador del reporte por persona que use los mismos servicios de Activity y del desglose, con el alcance de la jerarquía, sin notas reales y con los datos de demostración fijos.

## 9. Esfuerzo
Medido con `git diff --stat`: ≈700 líneas.

| Tarea | Estado | Volumen | Horas-agente |
|---|---|---|---|
| Conciliación | Hecho | lectura | 0,5 |
| Política común, registro, T0 y migración (backend) | Hecho | ~330 LoC, 175 LoC/h | 1,9 |
| Interfaz T0 y Activity Emails | Hecho | ~120 LoC, 60 LoC/h | 2,0 |
| Tests (integración y E2E) | Hecho | ~250 LoC, 120 LoC/h | 2,1 |
| **Total CP1** | | | **≈6,5** |
| CP2: plantillas estratégicas, destinatarios, generador por persona, resumen semanal del equipo | Pendiente de revisión | ~1.800-2.400 LoC | 18-26, **+10 % = 20-29** |
| CP3: Send test T3/T4 y la matriz de cinco casos | Pendiente | ~500-700 LoC | 5-7, **+10 % = 6-8** |
