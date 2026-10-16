"""Límites de tiempo y mensajes por paso del proveedor de correo.

Incidente (16-10-2026, DigitalOcean): Verify y Send Test Email con Microsoft
365 se quedaban esperando hasta que el servidor web cortaba (504/502) y la
pantalla sólo decía «Something went wrong». La red llegaba a Microsoft; lo que
no tenía límite era la conversación: `msal` sin `timeout` y 15 s por cada paso
y por cada una de las direcciones del servidor.

Aquí se comprueba que la conversación entera termina dentro del plazo, que el
error dice **en qué paso** falló y que el texto del proveedor no sale.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

from app.core.email import backends


@pytest.fixture
def plazos_cortos(monkeypatch):
    monkeypatch.setattr(backends, "TOTAL_DEADLINE_SECONDS", 1.5)
    monkeypatch.setattr(backends, "SMTP_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(backends, "CONNECT_ATTEMPT_SECONDS", 0.5)
    monkeypatch.setattr(backends, "TOKEN_TIMEOUT_SECONDS", 1)


@pytest.fixture
def servidor_mudo():
    """Acepta la conexión TCP y no dice nada: ni saludo SMTP ni cierre."""
    escucha = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    escucha.bind(("127.0.0.1", 0))
    escucha.listen(8)
    abiertas: list[socket.socket] = []
    parar = threading.Event()

    def aceptar():
        escucha.settimeout(0.2)
        while not parar.is_set():
            try:
                conexion, _ = escucha.accept()
                abiertas.append(conexion)
            except OSError:
                continue

    hilo = threading.Thread(target=aceptar, daemon=True)
    hilo.start()
    yield escucha.getsockname()[1]
    parar.set()
    hilo.join(timeout=1)
    for c in abiertas:
        c.close()
    escucha.close()


def _smtp(puerto: int) -> backends.SmtpEmailBackend:
    return backends.SmtpEmailBackend(
        host="127.0.0.1", port=puerto, use_tls=True, username="u", password="p", sender="s@x.com",
    )


def test_un_servidor_que_no_contesta_termina_dentro_del_plazo(plazos_cortos, servidor_mudo):
    inicio = time.monotonic()
    with pytest.raises(backends.EmailUnreachable) as fallo:
        _smtp(servidor_mudo).check()
    assert time.monotonic() - inicio < 3
    assert fallo.value.step == "smtp_timeout"
    assert backends.describir(fallo.value) == "The mail server did not answer in time."


def test_enviar_tampoco_se_cuelga(plazos_cortos, servidor_mudo):
    inicio = time.monotonic()
    with pytest.raises(backends.EmailUnreachable):
        _smtp(servidor_mudo).send(backends.OutgoingEmail(to="a@b.com", subject="s", body="b"))
    assert time.monotonic() - inicio < 3


def test_muchas_direcciones_que_no_responden_no_multiplican_la_espera(plazos_cortos, monkeypatch):
    """Ocho direcciones colgadas: el plazo total manda, no 8 × el de cada una."""
    reales = socket.getaddrinfo

    def ocho(host, port, *a, **k):
        destino = reales("10.255.255.1", port, socket.AF_INET, socket.SOCK_STREAM)[0]
        return [destino] * 8

    monkeypatch.setattr(backends.socket, "getaddrinfo", ocho)
    inicio = time.monotonic()
    with pytest.raises(backends.EmailUnreachable) as fallo:
        _smtp(587).check()
    assert time.monotonic() - inicio < 3
    assert fallo.value.step in ("smtp_timeout", "smtp_unreachable")


class _ReadTimeout(Exception):
    """Como `requests.exceptions.ReadTimeout`: el nombre basta."""


def _m365() -> backends.M365OAuthEmailBackend:
    return backends.M365OAuthEmailBackend(
        tenant_id="t", client_id="c", client_secret="s3cr3t-valor", sender="s@x.com",
    )


def test_el_token_tiene_limite_y_un_paso_propio(plazos_cortos, monkeypatch):
    import msal

    recibido = {}

    class _App:
        def __init__(self, *a, **k):
            recibido.update(k)

        def acquire_token_for_client(self, scopes):
            raise _ReadTimeout("read timed out after 1s")

    monkeypatch.setattr(msal, "ConfidentialClientApplication", _App)
    with pytest.raises(backends.EmailUnreachable) as fallo:
        _m365().check()
    assert 0 < recibido["timeout"] <= 1
    assert fallo.value.step == "token_timeout"
    assert "token request in time" in backends.describir(fallo.value)


def test_token_rechazado_solo_con_el_codigo(monkeypatch):
    import msal

    class _App:
        def __init__(self, *a, **k):
            pass

        def acquire_token_for_client(self, scopes):
            return {
                "error": "invalid_client",
                "error_description": "AADSTS7000215: Invalid client secret s3cr3t-valor for app c",
            }

    monkeypatch.setattr(msal, "ConfidentialClientApplication", _App)
    with pytest.raises(backends.EmailAuthFailed) as fallo:
        _m365().check()
    texto = backends.describir(fallo.value)
    assert fallo.value.step == "token_refused"
    assert texto.endswith("(invalid_client)")
    assert "AADSTS" not in texto and "s3cr3t" not in texto


def test_un_tenant_que_no_existe(monkeypatch):
    import msal

    class _App:
        def __init__(self, *a, **k):
            raise ValueError("Unable to get authority configuration for https://login.microsoftonline.com/t")

    monkeypatch.setattr(msal, "ConfidentialClientApplication", _App)
    with pytest.raises(backends.EmailUnreachable) as fallo:
        _m365().check()
    assert fallo.value.step == "token_unreachable"
    assert "Tenant ID" in backends.describir(fallo.value)


@pytest.mark.parametrize(
    ("paso", "codigo", "esperado"),
    [
        ("smtp_send_rejected", 554, "(554)"),
        ("smtp_auth_rejected", None, "SMTP.SendAsApp"),
        ("token_refused", "bad code <script>", "client secret"),
        ("paso_inventado", None, "did not answer or closed the connection"),
    ],
)
def test_describir_es_fijo_y_seguro(paso, codigo, esperado):
    exc = backends.EmailAuthFailed("texto del proveedor: secret=abc AADSTS9", step=paso, code=codigo)
    texto = backends.describir(exc)
    assert esperado in texto
    assert "secret=abc" not in texto and "AADSTS" not in texto and "<script>" not in texto
