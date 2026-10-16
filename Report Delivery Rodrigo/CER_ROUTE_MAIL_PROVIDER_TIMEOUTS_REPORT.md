# CER Route — Verify y la prueba de correo ya no se cuelgan: dicen qué falla

**Reporte** · 16 de octubre de 2026
**Status: COMPLETED WITH PENDING VALIDATION.** Corregido y probado en local.
- Pendiente: desplegar y repetir Verify en DigitalOcean.
- **El arreglo no hace que el correo salga** si Microsoft 365 está mal configurado, pero lo dirá en segundos.

## 1. El incidente
- **Qué se vio:** en DigitalOcean (`cerroute.cermanagementgroup.com`), **Verify** y **Send Test Email** del proveedor Microsoft 365 se quedaban esperando hasta que el servidor web cortaba con **504 / 502**. La pantalla solo decía «Something went wrong». No salió ningún correo.
- **Lo descartado, con evidencia de la consola de DigitalOcean:**
  - **No es la red:** el servidor llega a `smtp.office365.com:587`, `login.microsoftonline.com:443` y `graph.microsoft.com:443`.
  - **No es IPv6:** solo hay IPv4, y las 8 direcciones de Microsoft conectan en 0,0 s.
- **Lo confirmado:** el proveedor configurado es `M365OAuthEmailBackend` (`smtp.office365.com:587`), y la verificación misma (`check()`) se queda colgada.
- **Causa del cuelgue (CONFIRMED en el código):** la conversación con el proveedor **no tenía un límite total**.
  - `msal` (el token de Microsoft) se creaba **sin `timeout`**;
  - cada paso SMTP esperaba 15 s, y la conexión 15 s **por cada** dirección.
  - Si Microsoft no contesta, la espera supera el corte del servidor web.
- **Por qué no contesta Microsoft (UNVERIFIED):** la traza no se llegó a capturar. Lo más probable es la configuración de Microsoft 365 (tenant, aplicación, secreto, permisos o SMTP AUTH del buzón). Con este arreglo, Verify lo dirá.

## 2. El arreglo (`app/core/email/backends.py`)
- **Plazo total de 25 s** para toda la conversación: token, conexión, TLS, autenticación y envío. Cada paso usa solo lo que queda.
- **Token de Microsoft con límite de 10 s** (`msal.ConfidentialClientApplication(..., timeout=...)`).
- **5 s como máximo por dirección** al conectar, dentro del plazo total: ocho direcciones colgadas ya no suman ocho esperas.
- **El fallo dice su paso.** Código estable más un mensaje **fijo**; como mucho, un código corto validado:

| Paso | Mensaje |
|---|---|
| `token_timeout` | Microsoft Entra ID did not answer the token request in time. |
| `token_unreachable` | … did not answer the token request. Check the Tenant ID. |
| `token_refused` | … refused the token request. Check the Client ID, the client secret and its expiry. (`invalid_client`…) |
| `smtp_timeout` | The mail server did not answer in time. |
| `smtp_unreachable` | The mail server did not answer or closed the connection. |
| `smtp_auth_rejected` | … rejected the sign-in. Check SMTP.SendAsApp with admin consent, the Exchange service principal, the mailbox permission and that Authenticated SMTP is on. |
| `smtp_send_rejected` | … refused the message. Check that the app may send as the sender mailbox. (`554`…) |

- **Dónde se ve:**
  - **Verify** (`diagnostics._email_check_sync`) muestra ese mensaje;
  - **Send Test Email** (T0) y **Send test** (T1-T4) responden 502 en JSON `{outcome, step, message}`;
  - la auditoría guarda el `step`.
  - **Nunca** sale el texto del proveedor ni ningún secreto.
- **Sin cambios en:** el orden de proveedores, el respaldo, el límite de pruebas, el marcado `[TEST]`, los permisos, la base de datos (sin migraciones) y la pantalla, que ya enseñaba el mensaje del servidor.

## 3. Pruebas (local)

| Lote | Resultado |
|---|---|
| `tests/test_email_provider_timeouts.py` (nuevo): servidor que acepta y no contesta; envío; 8 direcciones colgadas (termina dentro del plazo, no en 8 esperas); token con límite y paso propio; token rechazado solo con el código; tenant inexistente; mensajes fijos y seguros | **10/10 PASS** |
| Verify y T0 de punta a punta con un Entra que no contesta (`test_verify_y_t0_dicen_el_paso_que_falla`) | **PASS** |
| Correo existente: recuperación de contraseña, diagnósticos, adaptadores M365/SMTP (XOAUTH2 exacto), pruebas de plantillas, cinco casos | **71/71 PASS** |
| Regresión completa | **1.467 recogidos, 1 FAIL preexistente**, exit 1, 1.221 s |

**Hallazgos durante el arreglo (CONFIRMED, corregidos antes de entregar):**
- `smtplib` convierte el tiempo agotado al leer la respuesta en `SMTPServerDisconnected`, que salía como «unreachable». Ahora se reconoce por su causa.
- El plazo se fijaba al definir la clase y no se podía ajustar; ahora se lee al crearlo.
- Los falsos de `msal` y SMTP de los tests de adaptadores se actualizaron al nuevo punto de conexión (`_abrir`) y al argumento `timeout`, que la librería real sí admite (`msal` 1.38.0).

## 4. Qué hacer después de desplegar
1. **Platform › Outbound email › Verify.** En menos de 30 s dirá `healthy` o el paso exacto que falla.
2. **Según el paso,** el administrador de Microsoft 365 revisa:

| Paso | Qué revisar |
|---|---|
| `token_timeout` / `token_unreachable` | Tenant ID; salida HTTPS del servidor a `login.microsoftonline.com` (ya comprobada) |
| `token_refused` | Client ID, Client Secret (¿vencido?) en Entra ID › App registrations |
| `smtp_auth_rejected` | Permiso **SMTP.SendAsApp** con consentimiento de administrador; `New-ServicePrincipal` y `Add-MailboxPermission` en Exchange Online; **Authenticated SMTP** activado en el buzón remitente |
| `smtp_send_rejected` | Que la aplicación pueda enviar como el buzón remitente |

3. Con `healthy`: **Send Test Email** y las cuatro pruebas de plantillas, y confirmar que llegan al buzón.

## 5. Regresión completa y Git
`uv run pytest tests --ignore=tests/e2e`: **1.467 recogidos, 1 FAIL**, exit 1, 1.221 s. Los otros 1.466 pasaron u omitieron; el desglose no quedó capturado.
- **Único fallo:** `test_provisioning_alignment::…twelve_and_two_capabilities`, **preexistente desde RTE09** (espera 12 capacidades para `route_admin` y hay 16). Sin relación con este cambio.
- **E2E: NOT RUN.** El frontend no cambia: la pantalla ya mostraba el mensaje del servidor.
- **Git:** rama `fix/mail-provider-timeouts`, desde `dev` `b756d36`. Sin migraciones.

## 6. Esfuerzo
≈ **2 horas-agente**, medido con `git diff --stat`: 9 archivos, +503 / −44 líneas.
