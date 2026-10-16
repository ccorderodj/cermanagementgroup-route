"""
Envío de correo.

De dónde sale el backend, en este orden
---------------------------------------
1. **El que fija un test** con `set_email_backend`. Manda siempre: un test que
   espera el correo en memoria no puede acabar mandándolo a Microsoft porque
   otro test dejó configurada la integración.
2. **El configurado en Settings** (fase 12): Microsoft 365 con OAuth o SMTP con
   usuario y contraseña, con sus credenciales descifradas al usarlas.
3. **El del entorno** (`EMAIL_BACKEND`): `console` en desarrollo, `memory` en
   tests, `smtp` para despliegues que aún lo configuran por variables.

Por qué OAuth para Microsoft 365
--------------------------------
CER tiene su correo en Exchange Online. Microsoft desactiva por defecto el
basic auth de SMTP AUTH a finales de diciembre de 2026, así que usuario y
contraseña contra Microsoft 365 es una prórroga, no una configuración.
`M365OAuthEmailBackend` pide un token con el flujo de credenciales de cliente y
se autentica con SASL XOAUTH2, que es lo que la documentación de Microsoft
describe para aplicaciones sin usuario interactivo.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage

from app.config import settings
from app.logger import logger

SMTP_TIMEOUT_SECONDS = 15


class EmailAuthFailed(RuntimeError):
    """El servidor o el proveedor de identidad rechazó las credenciales."""


class EmailUnreachable(RuntimeError):
    """No se llegó al servidor, o cortó la conversación."""


@dataclass
class OutgoingEmail:
    to: str
    subject: str
    body: str
    sender: str = ""


class EmailBackend:
    name = "base"
    sender: str | None = None

    def send(self, message: OutgoingEmail) -> None:  # pragma: no cover - interfaz
        raise NotImplementedError

    def check(self) -> None:
        """Abre la conversación y se autentica, **sin mandar nada**."""


class ConsoleEmailBackend(EmailBackend):
    """Deja constancia del envío sin exponer el cuerpo.

    El cuerpo lleva enlaces con testigos válidos: en un log normal no tiene nada
    que hacer. Para verlo durante el desarrollo hay que bajar a `DEBUG`.
    """

    name = "console"

    def send(self, message: OutgoingEmail) -> None:
        logger.info("EMAIL | to=%s subject=%s backend=console", message.to, message.subject)
        logger.debug("EMAIL BODY | to=%s | %s", message.to, message.body)


@dataclass
class MemoryEmailBackend(EmailBackend):
    """Cola en memoria para los tests."""

    outbox: list[OutgoingEmail] = field(default_factory=list)
    name = "memory"

    def send(self, message: OutgoingEmail) -> None:
        self.outbox.append(message)

    def clear(self) -> None:
        self.outbox.clear()

    def last_for(self, address: str) -> OutgoingEmail | None:
        for message in reversed(self.outbox):
            if message.to.lower() == address.lower():
                return message
        return None


def _mensaje(message: OutgoingEmail, sender: str) -> EmailMessage:
    email = EmailMessage()
    email["From"] = message.sender or sender
    email["To"] = message.to
    email["Subject"] = message.subject
    email.set_content(message.body)
    return email


#: El puerto 465 es SMTPS: el servidor exige TLS desde el primer byte, así que
#: mandarle un EHLO en claro y luego STARTTLS no funciona — hay que abrir la
#: conexión ya cifrada con `SMTP_SSL`. El 587 (y el resto) siguen el patrón
#: contrario: EHLO en claro y STARTTLS después. No hay bandera separada para
#: elegir uno u otro porque el propio puerto ya lo dice.
IMPLICIT_TLS_PORT = 465


class SmtpEmailBackend(EmailBackend):
    """SMTP con usuario y contraseña: SendGrid, Amazon SES, Mailgun, hosting compartido..."""

    name = "smtp_basic"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        use_tls: bool,
        username: str,
        password: str,
        sender: str,
    ) -> None:
        self.host, self.port, self.use_tls = host, int(port), use_tls
        self.username, self._password, self.sender = username, password, sender

    def _open(self) -> smtplib.SMTP:
        try:
            if self.use_tls and self.port == IMPLICIT_TLS_PORT:
                smtp = smtplib.SMTP_SSL(self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS)
                smtp.ehlo()
            else:
                smtp = smtplib.SMTP(self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS)
                smtp.ehlo()
                if self.use_tls:
                    smtp.starttls()
                    smtp.ehlo()
            if self.username:
                smtp.login(self.username, self._password)
            return smtp
        except smtplib.SMTPAuthenticationError as exc:
            raise EmailAuthFailed("The mail server rejected the configured credentials.") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailUnreachable("The mail server did not answer or closed the connection.") from exc

    def check(self) -> None:
        with self._open() as smtp:
            smtp.noop()

    def send(self, message: OutgoingEmail) -> None:
        with self._open() as smtp:
            smtp.send_message(_mensaje(message, self.sender))
        logger.info("EMAIL | to=%s subject=%s backend=%s", message.to, message.subject, self.name)


class M365OAuthEmailBackend(EmailBackend):
    """Exchange Online con OAuth 2.0 (credenciales de cliente) y SASL XOAUTH2."""

    name = "m365_oauth"
    SCOPE = "https://outlook.office365.com/.default"

    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        sender: str,
        host: str = "smtp.office365.com",
        port: int = 587,
    ) -> None:
        self.tenant_id, self.client_id, self._client_secret = tenant_id, client_id, client_secret
        self.sender, self.host, self.port = sender, host, int(port)

    def _token(self) -> str:
        import msal

        aplicacion = msal.ConfidentialClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self._client_secret,
        )
        try:
            resultado = aplicacion.acquire_token_for_client(scopes=[self.SCOPE])
        except Exception as exc:
            raise EmailUnreachable("Microsoft Entra ID did not answer the token request.") from exc
        token = (resultado or {}).get("access_token")
        if not token:
            # El mensaje de Entra puede repetir identificadores; sólo sale el código.
            codigo = (resultado or {}).get("error", "unknown_error")
            raise EmailAuthFailed(f"Microsoft Entra ID refused the token request ({codigo}).")
        return token

    def _xoauth2(self, token: str) -> str:
        return f"user={self.sender}\x01auth=Bearer {token}\x01\x01"

    def _open(self) -> smtplib.SMTP:
        token = self._token()
        try:
            smtp = smtplib.SMTP(self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS)
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            cadena = self._xoauth2(token)
            smtp.auth("XOAUTH2", lambda challenge=None: cadena)
            return smtp
        except smtplib.SMTPAuthenticationError as exc:
            raise EmailAuthFailed(
                "Exchange Online rejected the token. Check SMTP.SendAsApp, the service "
                "principal and the mailbox permission."
            ) from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailUnreachable("Exchange Online did not answer or closed the connection.") from exc

    def check(self) -> None:
        with self._open() as smtp:
            smtp.noop()

    def send(self, message: OutgoingEmail) -> None:
        with self._open() as smtp:
            smtp.send_message(_mensaje(message, self.sender))
        logger.info("EMAIL | to=%s subject=%s backend=%s", message.to, message.subject, self.name)


# ══ Selección ═══════════════════════════════════════════════════════════════════

_override: EmailBackend | None = None
_env_backend: EmailBackend | None = None


def backend_from_platform_config(key: str = "email") -> EmailBackend | None:
    """El backend configurado en Settings bajo `key`, o `None` si no hay uno utilizable.

    `key` es "email" (el proveedor preferido) o "email_fallback" (el segundo,
    coexistiendo con el primero -- ver `get_email_backend`). Cada uno guarda su
    propia fila de `platform_integration` y sus propios secretos, así que
    configurar uno no borra al otro.
    """
    from app.core.platform.config_service import platform_config

    estado = platform_config.integration(key)
    if estado is None or not estado.enabled or not estado.provider:
        return None
    c = estado.config
    if estado.provider == "m365_oauth":
        secreto = platform_config.secret(key, "client_secret")
        if not secreto:
            return None
        return M365OAuthEmailBackend(
            tenant_id=c["tenant_id"], client_id=c["client_id"], client_secret=secreto,
            sender=c["sender"], host=c.get("smtp_host", "smtp.office365.com"),
            port=int(c.get("smtp_port", 587)),
        )
    if estado.provider == "smtp_basic":
        return SmtpEmailBackend(
            host=c["host"], port=int(c.get("port", 587)),
            use_tls=str(c.get("use_tls", "true")).lower() == "true",
            username=c.get("username", ""),
            password=platform_config.secret(key, "password") or "",
            sender=c["sender"],
        )
    return None


def backend_from_environment() -> EmailBackend:
    global _env_backend
    if _env_backend is None:
        if settings.EMAIL_BACKEND == "smtp":
            _env_backend = SmtpEmailBackend(
                host=settings.SMTP_HOST, port=settings.SMTP_PORT, use_tls=settings.SMTP_USE_TLS,
                username=settings.SMTP_USER, password=settings.SMTP_PASSWORD,
                sender=settings.EMAIL_FROM,
            )
        elif settings.EMAIL_BACKEND == "memory":
            _env_backend = MemoryEmailBackend()
        else:
            _env_backend = ConsoleEmailBackend()
    return _env_backend


def get_email_backend() -> EmailBackend:
    """El backend que de verdad se usa para mandar.

    Prueba el proveedor preferido ("email"); si no está configurado, el de
    respaldo ("email_fallback"); si tampoco, el del entorno. Así conviven las
    dos implementaciones (M365 OAuth y SMTP con usuario y contraseña): un
    administrador puede tener la de respaldo lista y funcionando mientras
    termina de configurar la preferida, sin que ningún flujo se corte por
    falta de esa configuración (política de fallback de CER).
    """
    return (
        _override
        or backend_from_platform_config("email")
        or backend_from_platform_config("email_fallback")
        or backend_from_environment()
    )


def set_email_backend(backend: EmailBackend | None) -> None:
    """Fija el backend. Pensado para los tests."""
    global _override
    _override = backend


def send_email(*, to: str, subject: str, body: str) -> None:
    """Manda, probando cada proveedor disponible hasta que uno funcione.

    No basta con elegir el preferido una vez: si M365 está configurado pero su
    client secret venció, o el relé SMTP está caído, ese envío en concreto no
    debe perderse si el otro proveedor configurado sí puede mandarlo. Con
    `_override` fijado (tests) no hay cadena: gana siempre, sin tocar la red.
    """
    if _override is not None:
        remitente = getattr(_override, "sender", None) or settings.EMAIL_FROM
        _override.send(OutgoingEmail(to=to, subject=subject, body=body, sender=remitente))
        return

    candidatos = [
        b for b in (
            backend_from_platform_config("email"),
            backend_from_platform_config("email_fallback"),
            backend_from_environment(),
        )
        if b is not None
    ]
    for indice, backend in enumerate(candidatos):
        remitente = getattr(backend, "sender", None) or settings.EMAIL_FROM
        mensaje = OutgoingEmail(to=to, subject=subject, body=body, sender=remitente)
        es_el_ultimo = indice == len(candidatos) - 1
        try:
            backend.send(mensaje)
            return
        except (EmailAuthFailed, EmailUnreachable):
            if es_el_ultimo:
                raise
            logger.warning(
                "EMAIL | %s failed to send; falling back to the next configured provider",
                backend.name, exc_info=True,
            )
