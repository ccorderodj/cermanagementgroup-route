"""
La postura de seguridad del despliegue, de sólo lectura (S3).

Settings no enseñaba nada de la seguridad que la aplicación sí tiene: cuánto
dura una sesión, si las cookies son seguras, si la API documenta su superficie
a cualquiera. Esto la enseña, medida contra lo que exige producción.

**Ningún valor secreto sale de aquí.** De la clave de firma sale su longitud; de
la llave maestra, su huella.

`ok` responde a «¿está bien para producción?», no «¿está bien para este
entorno?». En desarrollo es normal ver elementos en rojo: el gate de postura
sólo se cierra en un despliegue de producción.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.core.platform.secrets import master_key_status


@dataclass(frozen=True)
class PostureItem:
    key: str
    title: str
    value: str
    ok: bool
    detail: str


def security_posture() -> list[PostureItem]:
    llave = master_key_status()
    origenes = settings.cors_origin_list
    return [
        PostureItem(
            "mode", "Environment", settings.MODE, settings.is_production,
            "Strict content security policy and secure cookies apply only in MODE=PROD.",
        ),
        PostureItem(
            "session_signing_key", "Session signing key",
            f"{len((settings.SECRET_KEY or '').strip())} characters", True,
            "Startup refuses empty, short or published keys. The value is never shown.",
        ),
        PostureItem(
            "session_lifetime", "Internal session lifetime",
            f"{settings.ACCESS_TOKEN_EXPIRE_MINUTES} minutes", True,
            "How long a signed-in staff session lasts.",
        ),
        PostureItem(
            "password_reset_lifetime", "Password reset link lifetime",
            f"{settings.PASSWORD_RESET_TOKEN_MINUTES} minutes", True,
            "Reset links are single-use and expire after this long.",
        ),
        PostureItem(
            "secure_cookies", "Secure cookies", "on" if settings.cookie_secure else "off",
            settings.cookie_secure,
            "Cookies are sent only over HTTPS when on. Off is expected on local http.",
        ),
        PostureItem(
            "content_security_policy", "Content security policy",
            "strict" if settings.is_production else "development (allows eval)",
            settings.is_production,
            "Production allows scripts only from this application, with no inline code and no eval.",
        ),
        PostureItem(
            "api_docs", "API documentation", "exposed" if settings.docs_enabled else "hidden",
            not settings.docs_enabled,
            "Published documentation describes the whole API surface to anyone who can reach it.",
        ),
        PostureItem(
            "metrics", "Metrics endpoint", "exposed at /metrics" if settings.ENABLE_METRICS else "off",
            not settings.ENABLE_METRICS,
            "In production metrics should be off or reachable only from the internal network.",
        ),
        PostureItem(
            "cors", "Cross-origin requests",
            ", ".join(origenes) if origenes else "same origin only",
            "*" not in origenes,
            "The application serves its own frontend, so no other origin needs access.",
        ),
        PostureItem(
            "master_key", "Credential encryption key",
            f"configured (key {llave['key_id']})" if llave["present"] else "missing",
            bool(llave["present"]),
            "Encrypts the credentials stored from Settings. Keep an offline copy.",
        ),
    ]
