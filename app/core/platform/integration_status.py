"""
El estado de una integración, calculado en un solo sitio.

Settings pinta la tarjeta, Diagnostics decide si la verifica y la preparación
para producción decide si su gate está cerrado. Si cada uno calculara el estado
por su cuenta, tarde o temprano Settings diría «verificada» mientras la
preparación dice «abierta», que es exactamente el defecto S1 que esta etapa
corrige.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.core.platform import providers as provider_defs
from app.core.platform.models import PlatformHealthCheck, PlatformIntegration, PlatformSecret
from app.core.platform.secrets import master_key_status, unseal


@dataclass
class IntegrationStatus:
    definition: provider_defs.Integration
    row: PlatformIntegration | None
    secrets: list[PlatformSecret]
    health: PlatformHealthCheck | None
    readiness: provider_defs.IntegrationReadiness

    @property
    def provider(self) -> provider_defs.Provider | None:
        return self.definition.provider(self.row.provider) if self.row else None


def master_key_matches(secrets: list[PlatformSecret], integration_key: str) -> bool:
    """Si la llave configurada descifra de verdad lo guardado.

    Que exista `PLATFORM_MASTER_KEY` no basta: si se cambió sin rotar, las filas
    siguen cifradas con la anterior y nada descifra.
    """
    if not master_key_status()["present"]:
        return False
    for s in secrets:
        try:
            unseal(
                integration_key=integration_key,
                secret_name=s.name,
                ciphertext=bytes(s.ciphertext),
                nonce=bytes(s.nonce),
                stored_key_id=s.key_id,
            )
        except Exception:
            return False
    return True


async def load_status(session, definition: provider_defs.Integration) -> IntegrationStatus:
    fila = await session.scalar(
        select(PlatformIntegration).where(PlatformIntegration.key == definition.key)
    )
    secretos = (
        (await session.execute(select(PlatformSecret).where(PlatformSecret.integration_id == fila.id)))
        .scalars()
        .all()
        if fila
        else []
    )
    salud = await session.scalar(
        select(PlatformHealthCheck).where(PlatformHealthCheck.capability_key == definition.key)
    )
    # Falla si la última comprobación es posterior a la verificación y no fue
    # sana: la verificación demostraba que funcionaba, y ya no funciona.
    fallando = bool(
        fila
        and fila.verified_at
        and salud
        and salud.last_status not in ("healthy", "not_applicable")
        and salud.last_checked_at
        and salud.last_checked_at > fila.verified_at
    )
    evaluacion = provider_defs.assess(
        definition,
        provider_key=fila.provider if fila else None,
        enabled=bool(fila.enabled) if fila else True,
        config=dict(fila.config or {}) if fila else {},
        secret_names={s.name for s in secretos},
        verified=bool(fila and fila.verified_at),
        master_key_ok=master_key_matches(list(secretos), definition.key),
        failing=fallando,
    )
    return IntegrationStatus(
        definition=definition, row=fila, secrets=list(secretos), health=salud, readiness=evaluacion
    )
