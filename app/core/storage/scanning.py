"""
El análisis de malware.

El requisito exige que un archivo se analice **antes** de estar normalmente
disponible (doc 08, AC-S04). Sin proveedor hay dos salidas y sólo una es
honesta: marcar los archivos como limpios, que sería afirmar un control que
nadie ejecutó, o dejarlos en cuarentena y decir que no hay proveedor. Esto hace
lo segundo, y con proveedor configurado analiza de verdad.

Dos proveedores (OD-08, elige CER)
----------------------------------
* **ClamAV**, dentro de la infraestructura de CER: los documentos no salen.
  Protocolo INSTREAM de clamd, sobre TCP.
* **Cloudmersive**, un servicio externo: cada documento viaja a un tercero.

Fallar cerrado
--------------
Si el escáner no contesta, el documento **no** se marca limpio ni se rechaza:
se queda en cuarentena, con el motivo. Una avería del escáner no puede ser una
puerta abierta, y tampoco una forma de perder la evidencia que el trabajador
subió.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

CLAMD_CHUNK = 64 * 1024


class ScanVerdict(StrEnum):
    """El resultado de mirar un archivo.

    `NOT_CONFIGURED` y `UNAVAILABLE` no dicen nada del archivo: dicen que nadie
    pudo mirarlo. Por eso los dos dejan el documento en cuarentena, y por eso se
    distinguen de `REJECTED`, que sí es un juicio sobre el archivo.
    """

    CLEAN = "clean"
    REJECTED = "rejected"
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ScanOutcome:
    verdict: ScanVerdict
    provider: str
    detail: str | None = None


class ScannerUnavailable(RuntimeError):
    """El escáner no contestó o contestó algo que no es un veredicto."""


class ScannerAuthFailed(ScannerUnavailable):
    """El proveedor rechazó las credenciales."""


class MalwareScanner(Protocol):
    name: str

    def scan(self, *, data: bytes, content_type: str) -> ScanOutcome:
        ...


class NotConfiguredScanner:
    """El proveedor que no existe.

    Devuelve siempre `NOT_CONFIGURED`. No mira `data` a propósito: cualquier
    heurística casera —«si empieza por MZ, malo»— sería el escáner de juguete
    que el requisito prohíbe simular.
    """

    name = "not_configured"

    def scan(self, *, data: bytes, content_type: str) -> ScanOutcome:
        return ScanOutcome(
            verdict=ScanVerdict.NOT_CONFIGURED,
            provider=self.name,
            detail=(
                "No malware scanning provider is configured. The document stays "
                "quarantined and is not available."
            ),
        )


class ClamAVScanner:
    """clamd por TCP, con el protocolo INSTREAM.

    El archivo viaja en trozos precedidos de su longitud (4 bytes, big-endian) y
    termina con un trozo de longitud cero. clamd contesta `stream: OK` o
    `stream: <firma> FOUND`.
    """

    name = "clamav"

    def __init__(self, *, host: str, port: int = 3310, timeout_seconds: int = 30) -> None:
        self.host, self.port, self.timeout = host, int(port), int(timeout_seconds)

    def _conversar(self, orden: bytes, cuerpo: bytes | None = None) -> str:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as s:
                s.sendall(b"z" + orden + b"\0")
                if cuerpo is not None:
                    for inicio in range(0, len(cuerpo), CLAMD_CHUNK):
                        trozo = cuerpo[inicio:inicio + CLAMD_CHUNK]
                        s.sendall(struct.pack("!L", len(trozo)) + trozo)
                    s.sendall(struct.pack("!L", 0))
                respuesta = b""
                while not respuesta.endswith(b"\0"):
                    parte = s.recv(4096)
                    if not parte:
                        break
                    respuesta += parte
        except OSError as exc:
            raise ScannerUnavailable(f"clamd at {self.host}:{self.port} did not answer") from exc
        return respuesta.rstrip(b"\0").decode("utf-8", "replace").strip()

    def ping(self) -> bool:
        return self._conversar(b"PING") == "PONG"

    def scan(self, *, data: bytes, content_type: str) -> ScanOutcome:
        respuesta = self._conversar(b"INSTREAM", data)
        if respuesta.endswith("OK"):
            return ScanOutcome(ScanVerdict.CLEAN, self.name, "No threat found.")
        if respuesta.endswith("FOUND"):
            firma = respuesta.split(":", 1)[-1].rsplit(" ", 1)[0].strip()
            return ScanOutcome(ScanVerdict.REJECTED, self.name, f"Threat found: {firma}.")
        raise ScannerUnavailable(f"clamd returned no verdict ({respuesta[:80]})")


class CloudmersiveScanner:
    """Cloudmersive Virus Scan API (`POST /virus/scan/file`).

    El contrato sigue la referencia pública de la API: cabecera `Apikey`, archivo
    en `inputFile`, y `CleanResult` en la respuesta. No se ha probado contra el
    servicio real porque no hay cuenta; los tests usan un transporte simulado.
    """

    name = "cloudmersive"

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "https://api.cloudmersive.com",
        timeout_seconds: int = 60,
        transport=None,
    ) -> None:
        self._api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout_seconds
        self._transport = transport

    def scan(self, *, data: bytes, content_type: str) -> ScanOutcome:
        import httpx

        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as cliente:
                respuesta = cliente.post(
                    f"{self.endpoint}/virus/scan/file",
                    headers={"Apikey": self._api_key},
                    files={"inputFile": ("upload", data, content_type)},
                )
        except httpx.HTTPError as exc:
            raise ScannerUnavailable("Cloudmersive did not answer") from exc

        if respuesta.status_code in (401, 403):
            raise ScannerAuthFailed("Cloudmersive rejected the API key")
        if respuesta.status_code >= 400:
            raise ScannerUnavailable(f"Cloudmersive answered HTTP {respuesta.status_code}")
        try:
            cuerpo = respuesta.json()
        except ValueError as exc:
            raise ScannerUnavailable("Cloudmersive returned no verdict") from exc

        if cuerpo.get("CleanResult") is True:
            return ScanOutcome(ScanVerdict.CLEAN, self.name, "No threat found.")
        if cuerpo.get("CleanResult") is False:
            nombres = [v.get("VirusName") for v in cuerpo.get("FoundViruses") or [] if v.get("VirusName")]
            return ScanOutcome(
                ScanVerdict.REJECTED, self.name,
                f"Threat found: {', '.join(nombres) or 'unnamed'}.",
            )
        raise ScannerUnavailable("Cloudmersive returned no verdict")


def scan_safely(scanner: MalwareScanner, *, data: bytes, content_type: str) -> ScanOutcome:
    """Analiza, y si el escáner falla, deja el documento en cuarentena con el motivo."""
    try:
        return scanner.scan(data=data, content_type=content_type)
    except ScannerAuthFailed:
        return ScanOutcome(
            ScanVerdict.UNAVAILABLE, scanner.name,
            "The scanner rejected its credentials. The document stays quarantined.",
        )
    except ScannerUnavailable as exc:
        return ScanOutcome(
            ScanVerdict.UNAVAILABLE, scanner.name,
            f"The scanner is unavailable ({exc}). The document stays quarantined.",
        )


def eicar_test_file() -> bytes:
    """El archivo de prueba estándar EICAR, que todo antivirus debe detectar.

    Se compone en tiempo de ejecución a propósito: escrito entero en el código
    fuente, el antivirus de la máquina de desarrollo pondría en cuarentena este
    mismo archivo.
    """
    partes = ("X5O!P%@AP[4", chr(92), "PZX54(P^)7CC)7}$", "EICAR-STANDARD-", "ANTIVIRUS-TEST-FILE!$H+H*")
    return "".join(partes).encode("ascii")


def get_scanner() -> MalwareScanner:
    """El escáner configurado en Settings, o el que no existe."""
    from app.core.platform.config_service import platform_config

    estado = platform_config.integration("malware_scanner")
    if estado is None or not estado.enabled:
        return NotConfiguredScanner()
    c = estado.config
    if estado.provider == "clamav" and c.get("host"):
        return ClamAVScanner(
            host=c["host"], port=int(c.get("port", 3310)),
            timeout_seconds=int(c.get("timeout_seconds", 30)),
        )
    if estado.provider == "cloudmersive":
        clave = platform_config.secret("malware_scanner", "api_key")
        if clave:
            return CloudmersiveScanner(
                api_key=clave, endpoint=c.get("endpoint", "https://api.cloudmersive.com")
            )
    return NotConfiguredScanner()


def document_is_available(scan_status: str) -> bool:
    """Si un documento puede entregarse por los caminos normales.

    Sólo `clean`. Uno en cuarentena existe, se lista y se audita; lo que no se
    puede es servirlo como si alguien lo hubiera revisado.
    """
    return scan_status == ScanVerdict.CLEAN.value
