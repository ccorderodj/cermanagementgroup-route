"""
Firma HMAC de webhooks: lo que acepta y lo que rechaza.

Sin base de datos: la firma es una función pura sobre secreto, marca de tiempo
y bytes del cuerpo.
"""

from __future__ import annotations

import pytest

from app.core.integration.signatures import (
    SignatureError,
    build_header,
    compute,
    parse_header,
    verify,
)

SECRETO = "whsec_test_secret"
CUERPO = b'{"hello":"world"}'
AHORA = 1_726_400_000


def test_a_signature_built_with_the_secret_verifies():
    cabecera = build_header(SECRETO, CUERPO, timestamp=AHORA)
    assert verify(SECRETO, cabecera, CUERPO, tolerance_seconds=300, now=AHORA + 10) == AHORA


def test_a_changed_body_does_not_verify():
    cabecera = build_header(SECRETO, CUERPO, timestamp=AHORA)
    with pytest.raises(SignatureError):
        verify(SECRETO, cabecera, CUERPO + b" ", tolerance_seconds=300, now=AHORA)


def test_another_secret_does_not_verify():
    cabecera = build_header("whsec_other", CUERPO, timestamp=AHORA)
    with pytest.raises(SignatureError):
        verify(SECRETO, cabecera, CUERPO, tolerance_seconds=300, now=AHORA)


def test_the_timestamp_is_signed_so_it_cannot_be_moved():
    firma = compute(SECRETO, AHORA, CUERPO)
    with pytest.raises(SignatureError):
        verify(SECRETO, f"t={AHORA + 1},v1={firma}", CUERPO, tolerance_seconds=300, now=AHORA)


def test_an_old_signature_is_rejected_as_a_replay():
    cabecera = build_header(SECRETO, CUERPO, timestamp=AHORA)
    with pytest.raises(SignatureError, match="tolerance"):
        verify(SECRETO, cabecera, CUERPO, tolerance_seconds=300, now=AHORA + 301)


def test_any_of_several_signatures_is_enough_during_a_rotation():
    vieja = compute("whsec_old", AHORA, CUERPO)
    nueva = compute(SECRETO, AHORA, CUERPO)
    cabecera = f"t={AHORA},v1={vieja},v1={nueva}"
    assert parse_header(cabecera).signatures == (vieja, nueva)
    assert verify(SECRETO, cabecera, CUERPO, tolerance_seconds=300, now=AHORA) == AHORA


@pytest.mark.parametrize("cabecera", [None, "", "v1=abc", "t=notanumber,v1=abc", "t=123"])
def test_a_malformed_header_is_rejected(cabecera):
    with pytest.raises(SignatureError):
        verify(SECRETO, cabecera, CUERPO, tolerance_seconds=300, now=AHORA)
