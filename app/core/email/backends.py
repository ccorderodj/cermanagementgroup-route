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

import re
import smtplib
import socket
import time
from dataclasses import dataclass, field
from email.message import EmailMessage

from app.config import settings
from app.logger import logger

SMTP_TIMEOUT_SECONDS = 15

#: Cuánto puede durar, **en total**, una conversación con el proveedor
#: (token + conexión + TLS + autenticación + envío). Por debajo del corte del
#: servidor web: si no, Verify y las pruebas acaban en un 504 que no dice nada.
TOTAL_DEADLINE_SECONDS = 25

#: Cuánto se espera a Microsoft Entra ID por el token. `msal` no pone límite
#: por su cuenta: sin esto, un Entra que no contesta colgaba la petición.
TOKEN_TIMEOUT_SECONDS = 10

#: Cuánto se espera a cada dirección del servidor al conectar. Un nombre puede
#: resolver a varias (`smtp.office365.com` da ocho): sin tope por intento, la
#: espera se multiplicaba por el número de direcciones.
CONNECT_ATTEMPT_SECONDS = 5


class EmailFailure(RuntimeError):
    """Un fallo del proveedor, con el **paso** en que ocurrió.

    `step` es un código estable para la pantalla y la auditoría:
    `token_timeout`, `token_unreachable`, `token_refused`, `smtp_unreachable`,
    `smtp_timeout`, `smtp_auth_rejected`, `smtp_send_rejected`. El mensaje nunca lleva secretos ni el
    texto del proveedor (sólo, como mucho, el código de error de Entra).
    """

    default_step = "smtp_unreachable"

    def __init__(self, message: str, *, step: str | None = None, code: str | int | None = None) -> None:
        super().__init__(message)
        self.step = step or self.default_step
        #: Un código corto del proveedor (`invalid_client`, `554`), si lo hay.
        self.code = code


#: Lo que se enseña en pantalla y en la API por cada paso. **Fijo**: el texto
#: de una excepción puede traer lo que el proveedor contestó, y eso no sale.
_MENSAJES: dict[str, str] = {
    "token_timeout": "Microsoft Entra ID did not answer the token request in time.",
    "token_unreachable": "Microsoft Entra ID did not answer the token request. Check the Tenant ID.",
    "token_refused": "Microsoft Entra ID refused the token request. Check the Client ID, the client secret and its expiry.",
    "smtp_unreachable": "The mail server did not answer or closed the connection.",
    "smtp_timeout": "The mail server did not answer in time.",
    "smtp_auth_rejected": (
        "The mail server rejected the sign-in. For Microsoft 365, check SMTP.SendAsApp with admin consent, "
        "the Exchange service principal, the mailbox permission and that Authenticated SMTP is on."
    ),
    "smtp_send_rejected": "The mail server refused the message. Check that the app may send as the sender mailbox.",
}
_CODIGO_SEGURO = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")


def describir(exc: EmailFailure) -> str:
    """El mensaje para la pantalla: el del paso y, si es seguro, el código."""
    texto = _MENSAJES.get(exc.step, _MENSAJES["smtp_unreachable"])
    codigo = str(exc.code) if exc.code is not None else ""
    return f"{texto} ({codigo})" if _CODIGO_SEGURO.match(codigo) else texto


class EmailAuthFailed(EmailFailure):
    """El servidor o el proveedor de identidad rechazó las credenciales."""

    default_step = "smtp_auth_rejected"


class EmailUnreachable(EmailFailure):
    """No se llegó al servidor, o cortó la conversación, o no contestó a tiempo."""

    default_step = "smtp_unreachable"


@dataclass
class OutgoingEmail:
    to: str
    subject: str
    body: str
    sender: str = ""
    #: Cabeceras extra, p. ej. la que marca un correo de prueba.
    headers: dict[str, str] = field(default_factory=dict)


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
    for nombre, valor in message.headers.items():
        email[nombre] = valor
    email.set_content(message.body)
    return email


#: El puerto 465 es SMTPS: el servidor exige TLS desde el primer byte, así que
#: mandarle un EHLO en claro y luego STARTTLS no funciona — hay que abrir la
#: conexión ya cifrada con `SMTP_SSL`. El 587 (y el resto) siguen el patrón
#: contrario: EHLO en claro y STARTTLS después. No hay bandera separada para
#: elegir uno u otro porque el propio puerto ya lo dice.
IMPLICIT_TLS_PORT = 465


class _Plazo:
    """El tiempo que le queda a una conversación con el proveedor."""

    def __init__(self, segundos: float | None = None) -> None:
        # Se lee al crear el plazo, no al definir la clase: así un cambio de
        # configuración (o un test) se aplica a la siguiente conversación.
        self._fin = time.monotonic() + (TOTAL_DEADLINE_SECONDS if segundos is None else segundos)

    def restante(self) -> float:
        quedan = self._fin - time.monotonic()
        if quedan <= 0:
            raise TimeoutError("deadline")
        return quedan

    def ajustar(self, smtp: smtplib.SMTP) -> None:
        """Lo que queda de plazo, como timeout del siguiente paso."""
        if smtp.sock is not None:
            smtp.sock.settimeout(min(SMTP_TIMEOUT_SECONDS, self.restante()))


def _conectar(host: str, port: int, plazo: _Plazo, source_address=None) -> socket.socket:
    """Prueba cada dirección del nombre con un tope por intento y el plazo total."""
    ultimo: OSError | None = None
    for familia, tipo, proto, _, direccion in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        sock = socket.socket(familia, tipo, proto)
        sock.settimeout(min(CONNECT_ATTEMPT_SECONDS, plazo.restante()))
        try:
            if source_address:
                sock.bind(source_address)
            sock.connect(direccion)
            sock.settimeout(min(SMTP_TIMEOUT_SECONDS, plazo.restante()))
            return sock
        except OSError as exc:
            ultimo = exc
            sock.close()
    raise ultimo or OSError(f"No address for {host}")


class _SMTP(smtplib.SMTP):
    """`smtplib.SMTP` que conecta respetando un `_Plazo`."""

    plazo: _Plazo

    def _get_socket(self, host, port, timeout):
        return _conectar(host, port, self.plazo, self.source_address)


class _SMTP_SSL(smtplib.SMTP_SSL):
    """Ídem con TLS desde el primer byte (puerto 465)."""

    plazo: _Plazo

    def _get_socket(self, host, port, timeout):
        sock = _conectar(host, port, self.plazo, self.source_address)
        return self.context.wrap_socket(sock, server_hostname=self._host)


def _abrir(clase, host: str, port: int, plazo: _Plazo) -> smtplib.SMTP:
    smtp = clase(timeout=SMTP_TIMEOUT_SECONDS)
    smtp.plazo = plazo
    # `smtplib` sólo guarda el nombre del servidor en `__init__`, no en
    # `connect()`; STARTTLS y TLS lo usan para validar el certificado (SNI).
    # Sin esto el TLS se intentaba con un nombre vacío (`ValueError`,
    # incidente 16-10-2026 en DigitalOcean).
    smtp._host = host
    smtp.connect(host, port)
    return smtp


def _es_tiempo(exc: BaseException) -> bool:
    """Si el fallo es, en el fondo, un tiempo agotado.

    `smtplib` convierte un `TimeoutError` al leer la respuesta del servidor en
    `SMTPServerDisconnected`; la causa original queda en `__context__`.
    """
    return isinstance(exc, TimeoutError) or isinstance(exc.__context__, TimeoutError)


def _sin_tiempo(servidor: str) -> EmailUnreachable:
    return EmailUnreachable(f"{servidor} did not answer in time.", step="smtp_timeout")


def _rechazado(servidor: str, codigo: int | None) -> EmailAuthFailed:
    """Autenticó pero no aceptó el mensaje: casi siempre el remitente no está
    autorizado a enviar como ese buzón. Sólo el código SMTP, nunca el texto."""
    detalle = f" (SMTP {codigo})" if codigo else ""
    return EmailAuthFailed(
        f"{servidor} refused the message{detalle}. Check that the app may send as the sender mailbox.",
        step="smtp_send_rejected",
        code=codigo,
    )


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

    def _open(self, plazo: _Plazo) -> smtplib.SMTP:
        try:
            if self.use_tls and self.port == IMPLICIT_TLS_PORT:
                smtp = _abrir(_SMTP_SSL, self.host, self.port, plazo)
                plazo.ajustar(smtp)
                smtp.ehlo()
            else:
                smtp = _abrir(_SMTP, self.host, self.port, plazo)
                plazo.ajustar(smtp)
                smtp.ehlo()
                if self.use_tls:
                    plazo.ajustar(smtp)
                    smtp.starttls()
                    plazo.ajustar(smtp)
                    smtp.ehlo()
            if self.username:
                plazo.ajustar(smtp)
                smtp.login(self.username, self._password)
            return smtp
        except smtplib.SMTPAuthenticationError as exc:
            raise EmailAuthFailed("The mail server rejected the configured credentials.") from exc
        except (smtplib.SMTPException, OSError) as exc:
            if _es_tiempo(exc):
                raise _sin_tiempo("The mail server") from exc
            raise EmailUnreachable("The mail server did not answer or closed the connection.") from exc

    def check(self) -> None:
        plazo = _Plazo()
        try:
            with self._open(plazo) as smtp:
                plazo.ajustar(smtp)
                smtp.noop()
        except TimeoutError as exc:
            raise _sin_tiempo("The mail server") from exc
        except (smtplib.SMTPException, OSError) as exc:
            if _es_tiempo(exc):
                raise _sin_tiempo("The mail server") from exc
            raise EmailUnreachable("The mail server closed the connection.") from exc

    def send(self, message: OutgoingEmail) -> None:
        plazo = _Plazo()
        try:
            with self._open(plazo) as smtp:
                plazo.ajustar(smtp)
                smtp.send_message(_mensaje(message, self.sender))
        except TimeoutError as exc:
            raise _sin_tiempo("The mail server") from exc
        except smtplib.SMTPResponseException as exc:
            raise _rechazado("The mail server", exc.smtp_code) from exc
        except smtplib.SMTPRecipientsRefused as exc:
            raise _rechazado("The mail server", None) from exc
        except (smtplib.SMTPException, OSError) as exc:
            if _es_tiempo(exc):
                raise _sin_tiempo("The mail server") from exc
            raise EmailUnreachable("The mail server closed the connection.") from exc
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

    def _token(self, plazo: _Plazo) -> str:
        import msal

        try:
            aplicacion = msal.ConfidentialClientApplication(
                self.client_id,
                authority=f"https://login.microsoftonline.com/{self.tenant_id}",
                client_credential=self._client_secret,
                timeout=min(TOKEN_TIMEOUT_SECONDS, plazo.restante()),
            )
            resultado = aplicacion.acquire_token_for_client(scopes=[self.SCOPE])
        except Exception as exc:
            # `requests` señala el tiempo agotado con su propia clase; no se
            # importa para no atar el código a la librería que use msal.
            if isinstance(exc, TimeoutError) or "Timeout" in type(exc).__name__:
                raise EmailUnreachable(
                    "Microsoft Entra ID did not answer the token request in time.", step="token_timeout"
                ) from exc
            # Un tenant que no existe o un authority mal escrito también caen
            # aquí (msal lo valida al crear la aplicación).
            raise EmailUnreachable(
                "Microsoft Entra ID did not answer the token request. Check the Tenant ID.",
                step="token_unreachable",
            ) from exc
        token = (resultado or {}).get("access_token")
        if not token:
            # El mensaje de Entra puede repetir identificadores; sólo sale el código.
            codigo = (resultado or {}).get("error", "unknown_error")
            raise EmailAuthFailed(
                f"Microsoft Entra ID refused the token request ({codigo}). "
                "Check the Client ID, the client secret and its expiry.",
                step="token_refused",
                code=codigo,
            )
        return token

    def _xoauth2(self, token: str) -> str:
        return f"user={self.sender}\x01auth=Bearer {token}\x01\x01"

    def _open(self, plazo: _Plazo) -> smtplib.SMTP:
        token = self._token(plazo)
        try:
            smtp = _abrir(_SMTP, self.host, self.port, plazo)
            plazo.ajustar(smtp)
            smtp.ehlo()
            plazo.ajustar(smtp)
            smtp.starttls()
            plazo.ajustar(smtp)
            smtp.ehlo()
            cadena = self._xoauth2(token)
            plazo.ajustar(smtp)
            smtp.auth("XOAUTH2", lambda challenge=None: cadena)
            return smtp
        except smtplib.SMTPAuthenticationError as exc:
            raise EmailAuthFailed(
                "Exchange Online rejected the token. Check SMTP.SendAsApp, the service "
                "principal, the mailbox permission and that Authenticated SMTP is on for the mailbox."
            ) from exc
        except (smtplib.SMTPException, OSError) as exc:
            if _es_tiempo(exc):
                raise _sin_tiempo("Exchange Online") from exc
            raise EmailUnreachable("Exchange Online did not answer or closed the connection.") from exc

    def check(self) -> None:
        plazo = _Plazo()
        try:
            with self._open(plazo) as smtp:
                plazo.ajustar(smtp)
                smtp.noop()
        except TimeoutError as exc:
            raise _sin_tiempo("Exchange Online") from exc
        except (smtplib.SMTPException, OSError) as exc:
            if _es_tiempo(exc):
                raise _sin_tiempo("Exchange Online") from exc
            raise EmailUnreachable("Exchange Online closed the connection.") from exc

    def send(self, message: OutgoingEmail) -> None:
        plazo = _Plazo()
        try:
            with self._open(plazo) as smtp:
                plazo.ajustar(smtp)
                smtp.send_message(_mensaje(message, self.sender))
        except TimeoutError as exc:
            raise _sin_tiempo("Exchange Online") from exc
        except smtplib.SMTPResponseException as exc:
            raise _rechazado("Exchange Online", exc.smtp_code) from exc
        except smtplib.SMTPRecipientsRefused as exc:
            raise _rechazado("Exchange Online", None) from exc
        except (smtplib.SMTPException, OSError) as exc:
            if _es_tiempo(exc):
                raise _sin_tiempo("Exchange Online") from exc
            raise EmailUnreachable("Exchange Online closed the connection.") from exc
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


def send_email(*, to: str, subject: str, body: str, headers: dict[str, str] | None = None) -> str:
    """Manda, probando cada proveedor disponible hasta que uno funcione.

    Devuelve el `name` del backend que lo aceptó (`console` y `memory` no
    mandan nada fuera del servidor), para que quien llama pueda decir con
    honestidad qué pasó.

    No basta con elegir el preferido una vez: si M365 está configurado pero su
    client secret venció, o el relé SMTP está caído, ese envío en concreto no
    debe perderse si el otro proveedor configurado sí puede mandarlo. Con
    `_override` fijado (tests) no hay cadena: gana siempre, sin tocar la red.
    """
    if _override is not None:
        remitente = getattr(_override, "sender", None) or settings.EMAIL_FROM
        _override.send(OutgoingEmail(to=to, subject=subject, body=body, sender=remitente, headers=dict(headers or {})))
        return _override.name

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
        mensaje = OutgoingEmail(to=to, subject=subject, body=body, sender=remitente, headers=dict(headers or {}))
        es_el_ultimo = indice == len(candidatos) - 1
        try:
            backend.send(mensaje)
            return backend.name
        except (EmailAuthFailed, EmailUnreachable):
            if es_el_ultimo:
                raise
            logger.warning(
                "EMAIL | %s failed to send; falling back to the next configured provider",
                backend.name, exc_info=True,
            )
