"""
Rotación de la llave maestra (D12-01).

Congela las dos cosas que hacen segura una rotación: que todo sigue funcionando
mientras conviven las dos llaves, y que al terminar ninguna credencial depende
ya de la anterior.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import settings
from app.core.platform import secrets
from app.core.platform.config_service import platform_config
from app.core.platform.models import PlatformSecret
from app.core.platform.rotate_master_key import rotate
from app.database import async_session_maker

SECRETO = "rotation-secret-0123456789"


async def test_rotation_re_encrypts_everything_with_the_new_key(seeded, alpha_client, monkeypatch):
    anterior = secrets.generate_master_key()
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY", anterior)
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY_PREVIOUS", "")

    await alpha_client.login(seeded.platform_admin.email)
    assert (await alpha_client.put("/api/platform/integrations/malware_scanner", json={
        "provider": "cloudmersive", "config": {},
    })).status_code == 200
    assert (await alpha_client.put(
        "/api/platform/integrations/malware_scanner/secrets/api_key", json={"value": SECRETO}
    )).status_code == 200

    nueva = secrets.generate_master_key()
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY", nueva)
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY_PREVIOUS", anterior)

    # Mientras conviven las dos llaves, la credencial sigue abriéndose.
    await platform_config.refresh()
    assert platform_config.secret("malware_scanner", "api_key") == SECRETO

    informe = await rotate()
    assert informe.rotated == 1

    # Sin la anterior, todo abre: ya nada depende de ella.
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY_PREVIOUS", "")
    await platform_config.refresh()
    assert platform_config.secret("malware_scanner", "api_key") == SECRETO

    async with async_session_maker() as session:
        fila = await session.scalar(select(PlatformSecret))
    assert fila.key_id == secrets.current_key_id()

    # Una segunda rotación no tiene nada que hacer.
    assert (await rotate()).rotated == 0


async def test_rotation_refuses_to_start_without_the_previous_key(seeded, alpha_client, monkeypatch):
    anterior = secrets.generate_master_key()
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY", anterior)
    await alpha_client.login(seeded.platform_admin.email)
    await alpha_client.put("/api/platform/integrations/malware_scanner", json={"provider": "cloudmersive", "config": {}})
    await alpha_client.put("/api/platform/integrations/malware_scanner/secrets/api_key", json={"value": SECRETO})

    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY", secrets.generate_master_key())
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY_PREVIOUS", "")

    with pytest.raises(secrets.MasterKeyUnavailable):
        await rotate()

    async with async_session_maker() as session:
        fila = await session.scalar(select(PlatformSecret))
    assert fila.key_id != secrets.current_key_id(), "no debe haber tocado nada"
