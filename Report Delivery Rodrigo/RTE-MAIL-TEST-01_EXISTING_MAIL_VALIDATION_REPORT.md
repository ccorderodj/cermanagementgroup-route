# RTE-MAIL-TEST-01: auditoría del correo existente y prueba controlada

**Reporte técnico** · 16 de octubre de 2026
**Instrucción:** `_cer_delivery/RTE-MAIL-TEST-01_EXISTING_MAIL_VALIDATION_V1_0.md`
**Status: PARTIAL.**
- La auditoría está hecha y la prueba controlada está construida y validada en local.
- **El envío real a un buzón de prueba (AC-05) está BLOCKED:** ningún entorno tiene un proveedor de correo configurado (sección 3).
- **La programación (AC-07) es un GAP:** MAIL-CP2 no está autorizado.

> **No se ha enviado ningún correo real.** No hay envíos programados ni a personas reales. Nada de lo de aquí activa el envío automático.

## 1. Resultado por checkpoint

| Parte | Estado | Evidencia |
|---|---|---|
| Inventario y matriz de brechas (AC-01) | **Completed** | Sección 2 |
| Secretos y configuración del proveedor (AC-02, AC-03) | **Completed** en código y tests; **BLOCKED** en entorno: no hay proveedor | Secciones 2 y 3 |
| Superficie de prueba controlada (B) | **Completed** | Secciones 4 y 6 |
| Envío real con recepción (AC-05) | **BLOCKED** | Falta configurar el proveedor en DigitalOcean (sección 3) |
| Programación mediodía / End Work +20 (C, AC-07) | **GAP**, no implementado | Sección 2; recomendación en la sección 8 |

## 2. Inventario del correo existente (verificado en código)

| Pieza | Ruta | Estado |
|---|---|---|
| «Área de Mail» | **No existe una sección «Mail».** Lo que hay: Platform › Integrations & Settings (proveedor), Platform › Diagnostics (comprobar y probar) y CER Route Configuration › Activity Emails (plantillas y destinatarios, RTE-NOT-01) | **DEVIATION** respecto de la premisa de la instrucción. La prueba controlada se añadió en **Activity Emails** |
| Adaptadores de proveedor | `app/core/email/backends.py`: `M365OAuthEmailBackend` (Exchange Online, OAuth + XOAUTH2), `SmtpEmailBackend` (SMTP básico, 465/587), `ConsoleEmailBackend` (desarrollo: solo registra), `MemoryEmailBackend` (tests) | **AS-BUILT/CONFIRMED** |
| Selección y respaldo | `get_email_backend` / `send_email`: Settings `email` → Settings `email_fallback` → entorno (`EMAIL_BACKEND`). Si uno falla por credenciales o red, prueba el siguiente | **AS-BUILT/CONFIRMED** |
| Secretos | Platform Settings: `platform_secret` cifrado con la llave maestra (`PLATFORM_MASTER_KEY`, solo en el entorno); el entorno admite `SMTP_PASSWORD`. Nunca salen por la API ni por los logs | **AS-BUILT/CONFIRMED** (tests de plataforma, 62/62) |
| Comprobación de conexión | `diagnostics._email_check_sync` → `backend.check()`: autentica **sin mandar**; resultado `healthy` / `auth_failed` / `unreachable` / `not_applicable` | **AS-BUILT/CONFIRMED**, solo administradores de plataforma |
| Prueba de proveedor | `POST /api/platform/integrations/{key}/test-message`: texto genérico a **cualquier** dirección; auditado en `platform_audit_event` | **AS-BUILT**, solo administradores de plataforma. **TECHNICAL DEBT:** no tiene lista de destinos ni límite (fuera del alcance de este cambio) |
| Plantillas y vista previa | `app/routers_api/activityemails/` (RTE-NOT-01): texto plano, variables permitidas, vista previa con datos ficticios sin proveedor | **AS-BUILT/CONFIRMED** |
| Destinatarios | `activity_email_preference`: dos interruptores, apagados por defecto, alcance jerárquico | **AS-BUILT/CONFIRMED** |
| Planificador | `app/core/platform/scheduler.py`: APScheduler en el proceso, con candado de líder en PostgreSQL. Lo usan millaje, odómetro, chequeos y webhooks | **AS-BUILT**. **No hay ningún job de correo motivacional: GAP** |
| Registro de entregas e idempotencia | No existe para correos de actividad. Patrón reutilizable: `missing_location_notification` | **GAP** (MAIL-CP2) |
| Jornada y zona horaria | `work_session.started_at/ended_at` (UTC) y `start_time_zone` del dispositivo | **AS-BUILT**. La zona del correo de mediodía está pendiente (DP-02 / DP-03) |
| Validación de correo | `email_validator` sintáctico (RTE-NOT-01). No hay correo «verificado» | **PARTIAL** |
| SPF / DKIM / DMARC | No se puede comprobar desde el código. M365 exige `SMTP.SendAsApp` y permiso sobre el buzón remitente | **PENDING VALIDATION** con quien administre el dominio |

## 3. Lista de comprobación del proveedor (sin valores secretos)
Leído en la base **local**, copia de DigitalOcean, solo con columnas no secretas.

| Elemento | Estado |
|---|---|
| Integración `email` (preferida) | **No configurada**: no hay fila |
| Integración `email_fallback` | **No configurada** |
| Secretos de correo guardados | **Ninguno** |
| Última comprobación programada (15-10-2026) | `email` y `email_fallback`: `not_applicable` |
| Pruebas de envío anteriores (`email.test_*`) | Ninguna |
| `EMAIL_BACKEND` del entorno DigitalOcean | **UNVERIFIED** (desde aquí no se ve). Si es `console`, nada sale del servidor |
| Remitente / dominio verificado | **UNVERIFIED** |

**Conclusión (LIKELY):** DigitalOcean no tiene correo saliente configurado, salvo cambios posteriores a la copia local. Por eso AC-05 está **BLOCKED**. Las claves que tiene el PO **no se han tocado**, como pide §A.

## 4. Lo añadido: prueba controlada en Activity Emails

| Pieza | Qué hace |
|---|---|
| `GET /api/activity-emails/test-targets` | Las direcciones a las que puede probar quien llama: **su propio correo** + `MAIL_TEST_RECIPIENTS`. Además, si hay proveedor real (sí/no, sin detalles) y el límite |
| `POST /api/activity-emails/templates/{tipo}/test-send` `{to}` | Manda la plantilla **guardada** con datos ficticios |
| `MAIL_TEST_RECIPIENTS` (`app/config.py`, `.env.example`) | Lista de destinos de prueba, separados por comas, sin secretos |
| `OutgoingEmail.headers`; `send_email` devuelve el backend que aceptó | Para marcar la prueba y saber qué pasó. Los demás usos no cambian |
| Pantalla: botón **Send test** en cada plantilla | Elige el destinatario de la lista, avisa si no hay proveedor y muestra el resultado |

**Barreras:**
- **Destino cerrado:** cualquier otra dirección da 403, incluidas personas del tenant, otro tenant o un destino libre. No hay CC ni BCC: un campo extra da 422.
- **Prueba marcada:** «[TEST]» en el asunto, aviso «CORREO DE PRUEBA — datos ficticios» al principio y cabecera `X-CER-Route-Test`.
- **Límite:** 5 pruebas por persona cada 15 minutos (429), contadas en `audit_event`, que es duradera y compartida entre réplicas.
- **Auditoría:** `audit_event` `activity_email_test/test_send` guarda plantilla, destino, resultado y backend. **No guarda** el cuerpo ni el texto del proveedor.
- **Aislamiento:** no lee ni cambia preferencias, jornadas ni actividades, ni ocupa ninguna clave de «un correo al día».
- **Resultados honestos:**

| Resultado | Significa |
|---|---|
| `accepted_by_provider` | Un proveedor real aceptó el mensaje. **No es «entregado»** (`delivered_confirmed: false` siempre) |
| `not_sent_development_backend` | Backend `console`: no salió del servidor |
| `captured_by_test_backend` | Backend de tests: no salió del servidor |
| `failed_auth` / `failed_unreachable` | 502, con un mensaje fijo y sin el texto del proveedor |

## 5. Criterios de aceptación

| AC | Estado | Evidencia |
|---|---|---|
| AC-01 inventario y brechas | VALIDATED | Sección 2 |
| AC-02 secretos seguros | VALIDATED (código) | Secretos cifrados y no expuestos (tests de plataforma); la prueba no registra cuerpo ni texto del proveedor: `test_credenciales_malas_502_sin_filtrar` |
| AC-03 comprobación de conexión clasificada | VALIDATED en local: `not_applicable` (sin proveedor), correcto. **PENDING** en DigitalOcean con proveedor |
| AC-04 las dos plantillas, con datos ficticios | VALIDATED: vista previa (RTE-NOT-01) + prueba de mediodía y de fin de jornada (`test_prueba_marcada…`, `test_aceptado_por_el_proveedor…`, E2E) |
| AC-05 envío real con recepción | **BLOCKED**: no hay proveedor configurado. Pasos en la sección 7 |
| AC-06 fallos sin datos sensibles | VALIDATED: credenciales malas → 502 `failed_auth` sin texto del proveedor; destino inválido → 403; sin permiso → 403; sin sesión → 401 |
| AC-07 programación con reloj simulado | **GAP**: no hay job ni registro de entregas; MAIL-CP2 |
| AC-08 la prueba no inscribe ni consume cuota | VALIDATED: `test_no_toca_preferencias_jornadas_ni_actividades` |
| AC-09 tenant/RBAC, regresión, responsive, auditoría | VALIDATED: tests negativos, regresión del correo existente 62/62, móvil en E2E, auditoría |
| AC-10 separa lo operativo de lo pendiente | Este documento |

## 6. Pruebas ejecutadas (local, base de tests)

| Lote | Comando | Resultado |
|---|---|---|
| Prueba controlada + Activity Emails | `uv run pytest tests/integration/test_activity_email_test_send.py tests/integration/test_activity_emails.py` | **30/30 PASS** |
| Cabecera en el mensaje SMTP real | `uv run pytest tests/test_email_test_header.py` | **2/2 PASS** |
| Correo existente: recuperación de contraseña, diagnósticos, adaptadores, catálogo, superficie pública | `uv run pytest tests/integration/test_password_reset_and_csrf.py tests/integration/test_platform_diagnostics.py tests/test_platform_adapters.py tests/test_permission_catalog.py tests/test_public_surface.py` | **62/62 PASS**, exit 0 |
| Navegador (Edge, build de producción) | `uv run pytest tests/e2e/test_activity_emails_browser.py -n 0` | **4/4 PASS** (incluida la prueba controlada) |
| Frontend | `npm run check` / `npm run build:prod` | exit 0 / exit 0 |
| Regresión completa | `uv run pytest tests --ignore=tests/e2e` | **1.424 recogidos, 2 FAIL** (1 preexistente, 1 corregido), exit 1, 1.253 s (sección 10) |

**Hallazgo corregido:** en escritorio, con las dos columnas, la fila de 4 botones se desbordaba y «Restore default» quedaba cortado (CONFIRMED en una captura). Ahora salta de línea (`sm:flex-wrap`). Capturas en `var/screenshots/activity-emails/`.

## 7. Para cerrar AC-05 (lo hace CER, en DigitalOcean)
1. **Platform › Integrations & Settings:** configurar el proveedor con las claves del PO.
   - M365: tenant, client id, client secret y remitente.
   - O SMTP: host, puerto, usuario, contraseña y remitente.
   - Las claves se escriben **solo ahí**; quedan cifradas.
2. **Verify:** debe dar `healthy` («Connected and authenticated… No message was sent»).
3. **Opcional:** `MAIL_TEST_RECIPIENTS` en las variables de la App, con el buzón de prueba.
4. **Activity Emails → Send test,** a tu propio correo o al buzón de prueba. Debe decir «Accepted by the mail provider…».
5. **Revisar la bandeja,** también la carpeta de spam, y guardar una captura. Ese es el único «entregado» que vale.
6. **Comprobar SPF, DKIM y DMARC del remitente** con quien administre el dominio.

## 8. Recomendación del siguiente paso
1. **Primero, cerrar AC-05** con la sección 7. No hay defectos del correo actual que corregir antes.
2. **Después, MAIL-CP2 (no autorizado):** envío programado de los correos motivacionales.
   - Un job en `PlatformScheduler`.
   - Un registro de entregas único por (compañía, persona, tipo, día local), con el patrón de `missing_location_notification`.
   - Volver a comprobar la elegibilidad al enviar.
   - **No enviar sin actividades.**
   - Mediodía en la zona aplicable (DP-02) y fin de jornada End Work +20 con aplazamiento si se reanuda.
   - Tests con reloj inyectable y despliegue escalonado.
   - Estimación: 17-26 horas-agente.
3. **Strategic Mail (MAIL-CP3 en adelante):** solo después de MAIL-CP2. Antes, DP-01 (hora de corte) y DP-02 (notas por correo).

## 9. Deuda y desviaciones
- **No existe un área «Mail»:** la prueba vive en Activity Emails. Si CER quiere un área Mail propia, es una decisión de navegación aparte.
- **La prueba de plataforma** (`test-message`) sigue aceptando cualquier destino, para administradores de plataforma. Conviene alinearla con la lista de destinos.
- **Sin migraciones,** permisos nuevos ni datos tocados. Web y móvil: sin cambios fuera de Activity Emails.

## 10. Regresión completa y Git
`uv run pytest tests --ignore=tests/e2e`: **1.424 recogidos, 2 FAIL**, exit 1, 1.253 s. Los otros 1.422 pasaron u omitieron; el desglose no quedó capturado.

| Fallo | Causa | Estado |
|---|---|---|
| `test_provisioning_alignment::…twelve_and_two_capabilities` | **Preexistente desde RTE09** (`CONFIRMED`): espera 12 capacidades para `route_admin` y hay 16 | Sin cambio; decisión pendiente de CER |
| `test_frontend_source_completeness::test_every_relative_import_resolves_to_a_versioned_file` | **CONFIRMED:** el test exige que todo import apunte a un archivo **versionado**, y `TestSendDialog.tsx` aún no estaba en git cuando corrió la regresión | Tras `git add`: **2/2 PASS** |

Git: rama `feature/rte-mail-test-01`, desde `dev` `798764e`. **Sin migraciones.**

## 11. Esfuerzo
Medido con `git diff --stat`: ≈600 líneas.

| Tarea | Estado | Volumen | Horas-agente |
|---|---|---|---|
| Auditoría e inventario | Hecho | lectura de ~10 módulos | 1,5 |
| Prueba controlada: backend | Hecho | ~220 LoC, 175 LoC/h | 1,3 |
| Prueba controlada: UI | Hecho | ~190 LoC, 60 LoC/h | 3,2 |
| Tests | Hecho | ~230 LoC, 120 LoC/h | 1,9 |
| **Total** | | | **≈8** |
| Cerrar AC-05 en DigitalOcean | CER | configuración | ~0,5 h humanas |
| MAIL-CP2 (no autorizado) | | ~1.200-1.600 LoC | 17-26 (+30 % integración incluido) |
