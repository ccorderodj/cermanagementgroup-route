"""
WP-2: configuración y secretos de plataforma en PostgreSQL (D12-01).

Lo que se congela no es que se pueda guardar una credencial —eso lo hace
cualquier formulario—, sino las garantías que hacen seguro guardarla en la
base:

* el valor **nunca** vuelve por la API, comprobado contra el valor real;
* en la base está cifrado, y un cifrado movido a otra ranura no descifra;
* sin llave no se guarda nada, y con la llave equivocada nada descifra;
* cada cambio deja traza, sin el valor, y la traza no se puede reescribir;
* guardar invalida la verificación anterior;
* sólo administración de plataforma.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from app.config import settings
from app.core.platform import secrets
from app.core.platform.models import PlatformAuditEvent, PlatformIntegration, PlatformSecret
from app.database import async_session_maker

SECRETO = "s3cr3t-Value~With.Symbols_1234567890"

M365 = {
    "provider": "m365_oauth",
    "config": {
        "tenant_id": "8a3c1f52-4b7e-4d19-9c0a-2f61d8e0b7a4",
        "client_id": "c41e97d0-6a28-4f3b-8e55-91b0d2a7c613",
        "sender": "no-reply@example.com",
    },
}


@pytest.fixture
def master_key(monkeypatch):
    clave = secrets.generate_master_key()
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY", clave)
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY_PREVIOUS", "")
    return clave


# ══ Cifrado ═════════════════════════════════════════════════════════════════════


def test_a_sealed_secret_opens_only_in_its_own_slot(master_key):
    sellado = secrets.seal(integration_key="email", secret_name="client_secret", plaintext=SECRETO)

    assert SECRETO.encode() not in sellado.ciphertext
    assert secrets.unseal(
        integration_key="email", secret_name="client_secret", ciphertext=sellado.ciphertext,
        nonce=sellado.nonce, stored_key_id=sellado.key_id,
    ) == SECRETO

    # El mismo cifrado copiado a la ranura de otra integración no descifra.
    with pytest.raises(secrets.SecretUndecryptable):
        secrets.unseal(
            integration_key="document_storage", secret_name="secret_access_key",
            ciphertext=sellado.ciphertext, nonce=sellado.nonce, stored_key_id=sellado.key_id,
        )


def test_the_previous_key_still_opens_during_a_rotation(monkeypatch, master_key):
    sellado = secrets.seal(integration_key="email", secret_name="client_secret", plaintext=SECRETO)

    nueva = secrets.generate_master_key()
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY", nueva)
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY_PREVIOUS", master_key)
    assert secrets.unseal(
        integration_key="email", secret_name="client_secret", ciphertext=sellado.ciphertext,
        nonce=sellado.nonce, stored_key_id=sellado.key_id,
    ) == SECRETO

    # Sin la anterior, lo cifrado con ella ya no se abre: hay que rotar antes.
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY_PREVIOUS", "")
    with pytest.raises(secrets.MasterKeyUnavailable):
        secrets.unseal(
            integration_key="email", secret_name="client_secret", ciphertext=sellado.ciphertext,
            nonce=sellado.nonce, stored_key_id=sellado.key_id,
        )


# ══ API ═══════════════════════════════════════════════════════════════════════════


async def _configurar_m365(client):
    respuesta = await client.put("/api/platform/integrations/email", json=M365)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def test_a_credential_is_stored_encrypted_and_never_returned(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.platform_admin.email)
    await _configurar_m365(alpha_client)

    guardado = await alpha_client.put(
        "/api/platform/integrations/email/secrets/client_secret",
        json={"value": SECRETO, "expires_at": "2028-09-10"},
    )
    assert guardado.status_code == 200, guardado.text
    assert SECRETO not in guardado.text
    cuerpo = guardado.json()
    assert cuerpo["status"] == "configured"
    assert [s for s in cuerpo["secrets"] if s["name"] == "client_secret"][0]["present"] is True

    for url in ("/api/platform/integrations", "/api/platform/integrations/email", "/api/platform/audit"):
        leido = await alpha_client.get(url)
        assert leido.status_code == 200, leido.text
        assert SECRETO not in leido.text, f"{url} devuelve el secreto"

    async with async_session_maker() as session:
        fila = await session.scalar(select(PlatformSecret).where(PlatformSecret.name == "client_secret"))
        assert SECRETO.encode() not in bytes(fila.ciphertext)
        assert len(bytes(fila.nonce)) == 12


async def test_invalid_configuration_is_rejected_field_by_field(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.platform_admin.email)
    malo = {**M365, "config": {**M365["config"], "tenant_id": "not-a-guid", "client_secret": "x"}}

    respuesta = await alpha_client.put("/api/platform/integrations/email", json=malo)

    assert respuesta.status_code == 422
    errores = " ".join(respuesta.json()["detail"])
    assert "Directory (tenant) ID" in errores
    assert "client_secret" in errores and "secret" in errores


async def test_a_credential_that_the_provider_does_not_have_is_refused(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.platform_admin.email)
    await _configurar_m365(alpha_client)

    respuesta = await alpha_client.put(
        "/api/platform/integrations/email/secrets/tenant_id", json={"value": "anything"}
    )
    assert respuesta.status_code == 422


async def test_without_a_master_key_nothing_is_stored(seeded, alpha_client, monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY", "")
    await alpha_client.login(seeded.platform_admin.email)
    await _configurar_m365(alpha_client)

    respuesta = await alpha_client.put(
        "/api/platform/integrations/email/secrets/client_secret", json={"value": SECRETO}
    )
    assert respuesta.status_code == 409
    assert "PLATFORM_MASTER_KEY" in respuesta.text


async def test_saving_clears_the_previous_verification(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.platform_admin.email)
    await _configurar_m365(alpha_client)
    async with async_session_maker() as session:
        await session.execute(text("UPDATE platform_integration SET verified_at = now() WHERE key = 'email'"))
        await session.commit()

    respuesta = await alpha_client.put(
        "/api/platform/integrations/email/secrets/client_secret", json={"value": SECRETO}
    )
    assert respuesta.json()["verified_at"] is None


async def test_a_stale_version_is_a_conflict(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.platform_admin.email)
    primera = await _configurar_m365(alpha_client)

    await alpha_client.put("/api/platform/integrations/email", json={**M365, "expected_version": primera["version"]})
    vieja = await alpha_client.put("/api/platform/integrations/email", json={**M365, "expected_version": primera["version"]})

    assert vieja.status_code == 409


async def test_changes_leave_a_trail_without_the_secret(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.platform_admin.email)
    await _configurar_m365(alpha_client)
    await alpha_client.put("/api/platform/integrations/email/secrets/client_secret", json={"value": SECRETO})

    async with async_session_maker() as session:
        eventos = (await session.execute(select(PlatformAuditEvent).order_by(PlatformAuditEvent.id))).scalars().all()
    acciones = [e.action for e in eventos]
    assert acciones == ["integration.updated", "secret.set"]
    assert all(e.actor_user_id == seeded.platform_admin.id for e in eventos)
    assert all(e.actor_role == "platform_admin" for e in eventos)
    assert eventos[1].changes["value"] == "changed"
    assert SECRETO not in str([e.changes for e in eventos])


async def test_the_platform_trail_cannot_be_rewritten(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.platform_admin.email)
    await _configurar_m365(alpha_client)

    async with async_session_maker() as session:
        with pytest.raises(Exception, match="append-only"):
            await session.execute(text("UPDATE platform_audit_event SET action = 'x'"))
        await session.rollback()


async def test_policies_are_validated_against_their_limits(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.platform_admin.email)

    fuera = await alpha_client.put("/api/platform/policies/upload", json={"value": {"max_bytes": 10}})
    assert fuera.status_code == 422

    intervalo = await alpha_client.put(
        "/api/platform/policies/health_checks", json={"value": {"interval_minutes": 1}}
    )
    assert intervalo.status_code == 422

    bien = await alpha_client.put(
        "/api/platform/policies/health_checks", json={"value": {"interval_minutes": 120}}
    )
    assert bien.status_code == 200, bien.text
    assert bien.json()["value"]["interval_minutes"] == 120
    assert bien.json()["customized"] is True


async def test_a_company_owner_cannot_touch_platform_settings(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    assert (await alpha_client.get("/api/platform/integrations")).status_code == 403
    assert (await alpha_client.put("/api/platform/integrations/email", json=M365)).status_code == 403
    assert (await alpha_client.put("/api/platform/policies/upload", json={"value": {}})).status_code == 403
