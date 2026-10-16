"""
Cifrado de las credenciales de plataforma (D12-01, fase 12).

Qué protege
-----------
Las credenciales que se configuran en Settings —el secreto de la aplicación de
Microsoft 365, la clave de acceso al almacén, la API key del escáner— viven en
PostgreSQL, relacionadas con su integración. Se guardan **cifradas**: un volcado
de la base, una réplica o una copia de seguridad no entregan ninguna.

La llave maestra (`PLATFORM_MASTER_KEY`) es lo único que no vive en la base. Si
viviera en ella, cifrar no protegería nada: quien tuviera el volcado tendría la
llave y el candado a la vez.

Cómo
----
AES-256-GCM, con un nonce aleatorio de 12 bytes por escritura. GCM autentica
además de cifrar: un cifrado manipulado no descifra a basura, falla.

Los datos asociados (AAD) son `integración:nombre`. Un cifrado copiado de la
ranura `email:client_secret` a `document_storage:secret_access_key` **no
descifra**, aunque la llave sea la misma. Sin eso, quien pudiera escribir en la
tabla podría cambiar una credencial por otra sin conocer ninguna.

Cada fila guarda el `key_id` de la llave con la que se cifró: una huella de la
llave, no la llave. Así una rotación sabe qué filas le quedan por re-cifrar, y
un descifrado con la llave equivocada se detecta antes de intentarlo.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import sys
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

NONCE_BYTES = 12
KEY_BYTES = 32


class MasterKeyUnavailable(RuntimeError):
    """No hay llave con la que cifrar, o falta la que cifró esta fila."""


class SecretUndecryptable(RuntimeError):
    """La llave existe pero el cifrado no corresponde: manipulado o de otra ranura."""


@dataclass(frozen=True)
class Sealed:
    ciphertext: bytes
    nonce: bytes
    key_id: str


def _decode(raw: str) -> bytes:
    try:
        material = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except (binascii.Error, ValueError) as exc:
        raise MasterKeyUnavailable("The platform master key is not valid base64.") from exc
    if len(material) != KEY_BYTES:
        raise MasterKeyUnavailable("The platform master key must decode to 32 bytes.")
    return material


def key_id(material: bytes) -> str:
    """Huella corta y estable de una llave. No revela la llave."""
    return hashlib.sha256(b"cer-platform-master-key:" + material).hexdigest()[:16]


def _available() -> dict[str, bytes]:
    """Las llaves con las que se puede descifrar: la actual y, si hay, la anterior."""
    llaves: dict[str, bytes] = {}
    for raw in (settings.PLATFORM_MASTER_KEY, settings.PLATFORM_MASTER_KEY_PREVIOUS):
        raw = (raw or "").strip()
        if raw:
            material = _decode(raw)
            llaves[key_id(material)] = material
    return llaves


def current_key_id() -> str | None:
    raw = (settings.PLATFORM_MASTER_KEY or "").strip()
    return key_id(_decode(raw)) if raw else None


def master_key_status() -> dict[str, str | bool | None]:
    """Lo que Settings puede enseñar de la llave. Nunca la llave."""
    return {
        "present": bool((settings.PLATFORM_MASTER_KEY or "").strip()),
        "key_id": current_key_id(),
        "previous_present": bool((settings.PLATFORM_MASTER_KEY_PREVIOUS or "").strip()),
    }


def _aad(integration_key: str, secret_name: str) -> bytes:
    return f"{integration_key}:{secret_name}".encode("utf-8")


def seal(*, integration_key: str, secret_name: str, plaintext: str) -> Sealed:
    raw = (settings.PLATFORM_MASTER_KEY or "").strip()
    if not raw:
        raise MasterKeyUnavailable(
            "PLATFORM_MASTER_KEY is not configured, so credentials cannot be stored."
        )
    material = _decode(raw)
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(material).encrypt(
        nonce, plaintext.encode("utf-8"), _aad(integration_key, secret_name)
    )
    return Sealed(ciphertext=ciphertext, nonce=nonce, key_id=key_id(material))


def unseal(
    *,
    integration_key: str,
    secret_name: str,
    ciphertext: bytes,
    nonce: bytes,
    stored_key_id: str,
) -> str:
    material = _available().get(stored_key_id)
    if material is None:
        raise MasterKeyUnavailable(
            "The key that encrypted this credential is not configured."
        )
    try:
        claro = AESGCM(material).decrypt(
            bytes(nonce), bytes(ciphertext), _aad(integration_key, secret_name)
        )
    except InvalidTag as exc:
        raise SecretUndecryptable(
            "The stored credential does not match its slot or was altered."
        ) from exc
    return claro.decode("utf-8")


def generate_master_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(KEY_BYTES)).decode("ascii")


if __name__ == "__main__":
    if sys.argv[1:] == ["generate"]:
        print(generate_master_key())
    else:
        raise SystemExit("Uso: python -m app.core.platform.secrets generate")
