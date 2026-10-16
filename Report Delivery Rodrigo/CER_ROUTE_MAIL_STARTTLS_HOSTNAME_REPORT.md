# CER Route — Send Test Email: error 500 al iniciar TLS (corregido)

**Reporte** · 16 de octubre de 2026
**Status: COMPLETED WITH PENDING VALIDATION.** Corregido y probado en local. Pendiente: desplegar y repetir la prueba en DigitalOcean.

## 1. Qué pasó
- **El síntoma:** en DigitalOcean, tras desplegar el MR !106, **Send Test Email** respondía **500**.
- **La traza** (Runtime Logs, 16-10-2026 22:47:52 UTC, petición `30fb9f5871b4`):
  ```
  backends.py, line 410, in _open → smtp.starttls()
  ssl.py … wrap_socket(..., server_hostname=self._host)
  ValueError: server_hostname cannot be an empty string or start with a leading dot.
  ```
- **Causa (CONFIRMED): defecto introducido en el MR !106.**
  - Para poder limitar el tiempo, la conexión SMTP se crea sin host y se conecta después (`_abrir`).
  - `smtplib` solo guarda el nombre del servidor (`_host`) en `__init__`, no en `connect()`.
  - STARTTLS intentó el TLS con un nombre vacío y `ssl` lo rechazó con un `ValueError` que no es un fallo del proveedor, así que salió como 500.
- **Por qué no lo detectaron los tests:** los del MR !106 usaban servidores sin TLS, y los de adaptadores sustituyen la conexión entera.
- **Lo que sí demuestra la traza:** el problema ya **no** es Microsoft 365.
  - **El token de Entra ID se obtuvo:** la petición llegó a STARTTLS en 786 ms.
  - **La conexión con `smtp.office365.com:587` funciona.**

## 2. El arreglo
`app/core/email/backends.py`, en `_abrir`: `smtp._host = host` antes de `connect()`. El TLS (STARTTLS y SMTPS) vuelve a validar el certificado con el nombre del servidor (SNI). Es una sola línea con su comentario.

## 3. Pruebas (local)

| Lote | Resultado |
|---|---|
| Test nuevo `test_starttls_usa_el_nombre_del_servidor`: un servidor SMTP de prueba que ofrece STARTTLS; se comprueba que el TLS se negocia con `server_hostname="127.0.0.1"` | **Sin el arreglo: FAIL** con el mismo `ValueError` de producción. **Con el arreglo: PASS** |
| Proveedor y adaptadores (`test_email_provider_timeouts.py`, `test_platform_adapters.py`) | **23/23 PASS** |
| Todo el correo: diagnósticos, recuperación de contraseña, pruebas de plantillas, cinco casos, política de pruebas | **73/73 PASS** |
| Regresión completa | **NOT RUN**: el cambio es una línea en la conexión SMTP, cubierta por los 73 tests de correo; se priorizó desbloquear la prueba en producción |

## 4. Después de desplegar
1. **Platform › Outbound email › Verify:** debe dar `healthy` o el paso que falla.
2. **Send Test Email** a tu correo:
   - «Accepted by m365_oauth…»: mira la bandeja (y spam).
   - «refused the message»: falta permiso para enviar como el buzón remitente.
   - «rejected the sign-in»: SMTP.SendAsApp, el registro en Exchange (service principal), el permiso sobre el buzón o Authenticated SMTP.

## 5. Git y esfuerzo
- **Rama:** `fix/mail-starttls-hostname`, desde `dev` `ebdb6b1`. Sin migraciones.
- **Esfuerzo:** ≈0,5 horas-agente.
