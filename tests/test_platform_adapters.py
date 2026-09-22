"""
WP-5: los adaptadores de terceros, contra dobles fieles.

**No son pruebas en vivo.** No hay cuenta de Microsoft 365, ni bucket de
Spaces, ni ClamAV, ni Cloudmersive en este entorno. Lo que se prueba es que
cada adaptador habla el protocolo que su proveedor documenta:

* S3: contra `moto`, que implementa la API de S3.
* ClamAV: contra un servidor TCP que habla INSTREAM como clamd.
* Cloudmersive: contra un transporte HTTP que responde con su contrato.
* Microsoft 365: el token y la conversación SMTP, con `msal` y `smtplib`
  sustituidos, comprobando la cadena XOAUTH2 exacta.

La verificación real la hace Diagnostics con las credenciales de CER.
"""

from __future__ import annotations

import socketserver
import struct
import threading

import httpx
import pytest

from app.core.email import backends
from app.core.storage.base import LocalFileStorage, S3CompatibleStorage
from app.core.storage.migrate_local_to_s3 import StoredObject, migrate_objects
from app.core.storage.scanning import (
    ClamAVScanner,
    CloudmersiveScanner,
    ScanVerdict,
    eicar_test_file,
    scan_safely,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# ══ S3 ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def s3_cliente():
    from moto import mock_aws

    with mock_aws():
        import boto3

        cliente = boto3.client("s3", region_name="us-east-1")
        cliente.create_bucket(Bucket="cer-evidence")
        yield cliente


def _almacen(cliente) -> S3CompatibleStorage:
    return S3CompatibleStorage(
        endpoint=None, region="us-east-1", bucket="cer-evidence",
        access_key_id="test", secret_access_key="test", prefix="evidence/", client=cliente,
    )


def test_s3_storage_keeps_the_server_generated_key_under_its_prefix(s3_cliente):
    almacen = _almacen(s3_cliente)

    objeto = almacen.put(data=PNG, content_type="image/png", original_filename="../../id.png", scope="uploads/7")

    assert objeto.storage_key.startswith("evidence/uploads/7/")
    assert ".." not in objeto.storage_key
    assert almacen.open(objeto.storage_key) == PNG
    assert almacen.exists(objeto.storage_key) is True
    assert almacen.exists("evidence/nope.png") is False


def test_s3_probe_objects_are_the_only_ones_that_can_be_deleted(s3_cliente):
    almacen = _almacen(s3_cliente)
    sonda = almacen.probe_key()
    almacen.put_existing(storage_key=sonda, data=b"probe", content_type="text/plain")

    almacen.delete_probe(sonda)
    assert almacen.exists(sonda) is False

    with pytest.raises(ValueError):
        almacen.delete_probe("evidence/uploads/7/real.png")


def test_migration_copies_with_the_same_key_and_refuses_altered_files(s3_cliente, tmp_path):
    local = LocalFileStorage(tmp_path)
    bueno = local.put(data=PNG, content_type="image/png", original_filename="a.png", scope="uploads/1")
    alterado = local.put(data=PNG + b"x", content_type="image/png", original_filename="b.png", scope="uploads/1")
    destino = _almacen(s3_cliente)
    objetos = [
        StoredObject(bueno.storage_key, bueno.content_hash, "image/png"),
        # La base guarda la huella del original; el archivo local ya no coincide.
        StoredObject(alterado.storage_key, bueno.content_hash, "image/png"),
        StoredObject("uploads/1/missing.png", bueno.content_hash, "image/png"),
    ]

    en_seco = migrate_objects(objetos, source=local, target=destino, apply=False)
    assert en_seco.copied == [bueno.storage_key]
    assert destino.exists(bueno.storage_key) is False, "en seco no escribe"

    real = migrate_objects(objetos, source=local, target=destino, apply=True)
    assert real.copied == [bueno.storage_key]
    assert real.hash_mismatch == [alterado.storage_key]
    assert real.missing_locally == ["uploads/1/missing.png"]
    assert destino.open(bueno.storage_key) == PNG

    otra_vez = migrate_objects(objetos, source=local, target=destino, apply=True)
    assert otra_vez.copied == [] and otra_vez.already_present == [bueno.storage_key]


# ══ ClamAV ═══════════════════════════════════════════════════════════════════════


class _ClamdFalso(socketserver.BaseRequestHandler):
    """Habla INSTREAM como clamd: `z<orden>\\0`, trozos con longitud, cero final."""

    def handle(self):
        orden = b""
        while not orden.endswith(b"\0"):
            orden += self.request.recv(1)
        if orden == b"zPING\0":
            self.request.sendall(b"PONG\0")
            return
        datos = b""
        while True:
            longitud = struct.unpack("!L", self._leer(4))[0]
            if longitud == 0:
                break
            datos += self._leer(longitud)
        if eicar_test_file() in datos:
            self.request.sendall(b"stream: Eicar-Test-Signature FOUND\0")
        else:
            self.request.sendall(b"stream: OK\0")

    def _leer(self, n):
        trozo = b""
        while len(trozo) < n:
            trozo += self.request.recv(n - len(trozo))
        return trozo


@pytest.fixture
def clamd():
    servidor = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _ClamdFalso)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield servidor.server_address
    servidor.shutdown()
    servidor.server_close()


def test_clamav_detects_the_standard_test_file_and_passes_a_clean_one(clamd):
    host, puerto = clamd
    escaner = ClamAVScanner(host=host, port=puerto, timeout_seconds=5)

    assert escaner.ping() is True
    limpio = escaner.scan(data=PNG * 2000, content_type="image/png")  # varios trozos
    assert limpio.verdict == ScanVerdict.CLEAN
    infectado = escaner.scan(data=eicar_test_file(), content_type="application/pdf")
    assert infectado.verdict == ScanVerdict.REJECTED
    assert "Eicar-Test-Signature" in infectado.detail


def test_an_unreachable_scanner_leaves_the_document_quarantined():
    escaner = ClamAVScanner(host="127.0.0.1", port=1, timeout_seconds=1)

    resultado = scan_safely(escaner, data=PNG, content_type="image/png")

    assert resultado.verdict == ScanVerdict.UNAVAILABLE
    assert "quarantined" in resultado.detail


# ══ Cloudmersive ════════════════════════════════════════════════════════════════


def _cloudmersive(respuesta: httpx.Response, vistos: list) -> CloudmersiveScanner:
    def manejar(peticion: httpx.Request) -> httpx.Response:
        vistos.append(peticion)
        return respuesta

    return CloudmersiveScanner(api_key="k-123", transport=httpx.MockTransport(manejar))


def test_cloudmersive_sends_the_key_and_reads_its_verdict():
    vistos: list = []
    limpio = _cloudmersive(httpx.Response(200, json={"CleanResult": True}), vistos)
    assert limpio.scan(data=PNG, content_type="image/png").verdict == ScanVerdict.CLEAN
    assert vistos[0].headers["Apikey"] == "k-123"
    assert vistos[0].url.path == "/virus/scan/file"

    infectado = _cloudmersive(
        httpx.Response(200, json={"CleanResult": False, "FoundViruses": [{"VirusName": "EICAR"}]}), []
    )
    resultado = infectado.scan(data=PNG, content_type="image/png")
    assert resultado.verdict == ScanVerdict.REJECTED and "EICAR" in resultado.detail


def test_a_rejected_cloudmersive_key_is_reported_without_releasing_anything():
    escaner = _cloudmersive(httpx.Response(401, json={}), [])

    resultado = scan_safely(escaner, data=PNG, content_type="image/png")

    assert resultado.verdict == ScanVerdict.UNAVAILABLE
    assert "credentials" in resultado.detail


# ══ Microsoft 365 ═══════════════════════════════════════════════════════════════


class _SmtpFalso:
    ultimo = None

    def __init__(self, host, port, timeout):
        self.host, self.port, self.pasos = host, port, []
        _SmtpFalso.ultimo = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        self.pasos.append("ehlo")

    def starttls(self):
        self.pasos.append("starttls")

    def auth(self, mecanismo, objeto):
        self.pasos.append(("auth", mecanismo, objeto()))

    def noop(self):
        self.pasos.append("noop")

    def send_message(self, mensaje):
        self.pasos.append(("send", mensaje["From"], mensaje["To"]))


def _m365(monkeypatch, resultado_token):
    class _AppFalsa:
        def __init__(self, client_id, authority, client_credential):
            _AppFalsa.args = (client_id, authority, client_credential)

        def acquire_token_for_client(self, scopes):
            _AppFalsa.scopes = scopes
            return resultado_token

    import msal

    monkeypatch.setattr(msal, "ConfidentialClientApplication", _AppFalsa)
    monkeypatch.setattr(backends.smtplib, "SMTP", _SmtpFalso)
    backend = backends.M365OAuthEmailBackend(
        tenant_id="8a3c1f52-4b7e-4d19-9c0a-2f61d8e0b7a4",
        client_id="c41e97d0-6a28-4f3b-8e55-91b0d2a7c613",
        client_secret="shh", sender="no-reply@example.com",
    )
    return backend, _AppFalsa


def test_m365_authenticates_with_the_exact_xoauth2_string(monkeypatch):
    backend, app = _m365(monkeypatch, {"access_token": "tok-abc"})

    backend.send(backends.OutgoingEmail(to="user@example.com", subject="Hi", body="x"))

    assert app.args[1] == "https://login.microsoftonline.com/8a3c1f52-4b7e-4d19-9c0a-2f61d8e0b7a4"
    assert app.scopes == ["https://outlook.office365.com/.default"]
    pasos = _SmtpFalso.ultimo.pasos
    assert pasos[:3] == ["ehlo", "starttls", "ehlo"], "STARTTLS antes de autenticar"
    assert pasos[3] == (
        "auth", "XOAUTH2",
        "user=no-reply@example.com\x01auth=Bearer tok-abc\x01\x01",
    )
    assert pasos[4] == ("send", "no-reply@example.com", "user@example.com")


def test_a_refused_token_is_an_authentication_failure_without_details(monkeypatch):
    backend, _ = _m365(
        monkeypatch,
        {"error": "invalid_client", "error_description": "AADSTS7000215 for app c41e97d0..."},
    )

    with pytest.raises(backends.EmailAuthFailed) as exc:
        backend.check()
    assert "invalid_client" in str(exc.value)
    assert "c41e97d0" not in str(exc.value)


def test_a_test_backend_always_wins_over_the_configured_one(monkeypatch):
    memoria = backends.MemoryEmailBackend()
    backends.set_email_backend(memoria)
    try:
        monkeypatch.setattr(backends, "backend_from_platform_config", lambda key="email": _SmtpFalso)
        assert backends.get_email_backend() is memoria
    finally:
        backends.set_email_backend(None)


def test_sending_falls_back_to_the_second_provider_when_the_first_is_not_configured(monkeypatch):
    """D-coexist: M365 sin configurar todavía no bloquea el correo si smtp_basic
    (por ejemplo, cPanel) sí lo está bajo "email_fallback"."""
    respaldo = backends.MemoryEmailBackend()

    def _por_clave(key: str = "email"):
        return respaldo if key == "email_fallback" else None

    monkeypatch.setattr(backends, "backend_from_platform_config", _por_clave)

    backends.send_email(to="user@example.com", subject="Hi", body="x")

    assert respaldo.last_for("user@example.com") is not None


def test_sending_falls_back_when_the_preferred_provider_fails_to_send(monkeypatch):
    """No basta con que el preferido esté configurado: si falla al mandar (secret
    vencido, relé caído), el correo debe salir igual por el que sí funciona."""
    respaldo = backends.MemoryEmailBackend()

    class _PreferidoRoto(backends.EmailBackend):
        name = "m365_oauth"
        sender = "no-reply@example.com"

        def send(self, message):
            raise backends.EmailAuthFailed("client secret expired")

    preferido = _PreferidoRoto()

    def _por_clave(key: str = "email"):
        return preferido if key == "email" else respaldo

    monkeypatch.setattr(backends, "backend_from_platform_config", _por_clave)

    backends.send_email(to="user@example.com", subject="Hi", body="x")

    assert respaldo.last_for("user@example.com") is not None
