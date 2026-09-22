"""
Firma de webhooks: HMAC-SHA256 sobre `timestamp.cuerpo`.

Cabecera (misma forma en las dos direcciones):

    X-CER-Signature: t=1726412345,v1=5257a869e7ecebeda32affa62cdca3fa51cad7e77a0e56ff536d0ce8e108d8bd

* `t` es la marca de tiempo Unix del emisor. Entra en lo firmado, así que no se
  puede cambiar sin invalidar la firma, y el receptor rechaza las que están
  fuera de `WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS` (anti-replay).
* `v1` es el HMAC en hexadecimal. Durante una rotación de secreto el emisor
  puede enviar varios `v1=`: basta con que uno corresponda.
* Se firma el **cuerpo exacto en bytes**, no el JSON reinterpretado: dos
  serializaciones del mismo objeto no dan los mismos bytes.
* La comparación es en tiempo constante.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass

SIGNATURE_HEADER = "X-CER-Signature"
EVENT_ID_HEADER = "X-CER-Event-Id"
EVENT_TYPE_HEADER = "X-CER-Event-Type"
SOURCE_APP_HEADER = "X-CER-Source-App"
CORRELATION_HEADER = "X-Correlation-ID"
SCHEME = "v1"


class SignatureError(ValueError):
    """La firma no es válida. El mensaje no revela cuál de las comprobaciones falló
    más allá de lo necesario para diagnosticar desde la contraparte."""


@dataclass(frozen=True)
class ParsedSignature:
    timestamp: int
    signatures: tuple[str, ...]


def compute(secret: str, timestamp: int, body: bytes) -> str:
    firmado = str(timestamp).encode("ascii") + b"." + body
    return hmac.new(secret.encode("utf-8"), firmado, hashlib.sha256).hexdigest()


def build_header(secret: str, body: bytes, *, timestamp: int | None = None) -> str:
    marca = int(time.time()) if timestamp is None else int(timestamp)
    return f"t={marca},{SCHEME}={compute(secret, marca, body)}"


def parse_header(value: str | None) -> ParsedSignature:
    if not value:
        raise SignatureError("Missing signature header.")
    marca: int | None = None
    firmas: list[str] = []
    for parte in value.split(","):
        clave, _, valor = parte.strip().partition("=")
        if clave == "t":
            try:
                marca = int(valor)
            except ValueError as exc:
                raise SignatureError("Malformed signature timestamp.") from exc
        elif clave == SCHEME and valor:
            firmas.append(valor)
    if marca is None or not firmas:
        raise SignatureError("Malformed signature header.")
    return ParsedSignature(timestamp=marca, signatures=tuple(firmas))


def verify(
    secret: str,
    header: str | None,
    body: bytes,
    *,
    tolerance_seconds: int,
    now: int | None = None,
) -> int:
    """Devuelve la marca de tiempo firmada si todo es válido; si no, `SignatureError`."""
    parsed = parse_header(header)
    ahora = int(time.time()) if now is None else int(now)
    if abs(ahora - parsed.timestamp) > tolerance_seconds:
        raise SignatureError("Signature timestamp is outside the allowed tolerance.")
    esperada = compute(secret, parsed.timestamp, body)
    if not any(hmac.compare_digest(esperada, candidata) for candidata in parsed.signatures):
        raise SignatureError("Signature does not match.")
    return parsed.timestamp


def body_sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()
