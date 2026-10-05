"""
La configuración de plataforma en ejecución: base primero, entorno de respaldo.

Por qué una instantánea
-----------------------
Quien usa la configuración —el backend de correo, el almacén, el escáner— se
llama desde código síncrono (`send_email`) y en cada subida de archivo. No puede
consultar la base cada vez. Así que el servicio mantiene una **instantánea** en
memoria: integraciones, secretos todavía cifrados y políticas.

Cómo se mantiene al día
-----------------------
* Quien escribe llama a `refresh()` al terminar: la instancia que atendió el
  cambio lo ve en el acto.
* La escritura emite `NOTIFY platform_config_changed`, y cada instancia escucha
  con `listen_for_changes()`: las demás réplicas se enteran sin esperar.
* Si la escucha se cae, `ensure_fresh()` recarga cuando la instantánea tiene más
  de `MAX_AGE_SECONDS`.

Los secretos se descifran **al usarlos**, no al cargar: en memoria viajan
cifrados, y un volcado del proceso no los entrega en claro.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select, text

from app.config import settings
from app.core.platform import policies as policy_defs
from app.core.platform.secrets import unseal
from app.database import async_session_maker
from app.logger import logger

CHANNEL = "platform_config_changed"
MAX_AGE_SECONDS = 30


@dataclass(frozen=True)
class SecretEntry:
    name: str
    ciphertext: bytes
    nonce: bytes
    key_id: str
    set_at: datetime | None
    expires_at: datetime | None


@dataclass(frozen=True)
class IntegrationState:
    key: str
    provider: str | None
    enabled: bool
    config: dict
    secrets: dict[str, SecretEntry]
    verified_at: datetime | None
    version: int


@dataclass(frozen=True)
class Snapshot:
    integrations: dict[str, IntegrationState] = field(default_factory=dict)
    policies: dict[str, dict] = field(default_factory=dict)
    loaded_at: float = 0.0


class PlatformConfig:
    def __init__(self) -> None:
        self._snapshot = Snapshot()
        self._lock = asyncio.Lock()

    def snapshot(self) -> Snapshot:
        return self._snapshot

    def reset(self) -> None:
        """Vuelve a la instantánea vacía. Lo usan los tests entre casos."""
        self._snapshot = Snapshot()

    async def refresh(self) -> Snapshot:
        from app.core.platform.models import (
            PlatformIntegration,
            PlatformPolicy,
            PlatformSecret,
        )

        async with self._lock:
            async with async_session_maker() as session:
                integraciones = (await session.execute(select(PlatformIntegration))).scalars().all()
                secretos = (await session.execute(select(PlatformSecret))).scalars().all()
                politicas = (await session.execute(select(PlatformPolicy))).scalars().all()

            por_integracion: dict[int, dict[str, SecretEntry]] = {}
            for s in secretos:
                por_integracion.setdefault(s.integration_id, {})[s.name] = SecretEntry(
                    name=s.name,
                    ciphertext=bytes(s.ciphertext),
                    nonce=bytes(s.nonce),
                    key_id=s.key_id,
                    set_at=s.set_at,
                    expires_at=s.expires_at,
                )

            self._snapshot = Snapshot(
                integrations={
                    i.key: IntegrationState(
                        key=i.key,
                        provider=i.provider,
                        enabled=bool(i.enabled),
                        config=dict(i.config or {}),
                        secrets=por_integracion.get(i.id, {}),
                        verified_at=i.verified_at,
                        version=i.version,
                    )
                    for i in integraciones
                },
                policies={p.key: dict(p.value or {}) for p in politicas},
                loaded_at=time.monotonic(),
            )
            return self._snapshot

    async def ensure_fresh(self) -> Snapshot:
        if time.monotonic() - self._snapshot.loaded_at > MAX_AGE_SECONDS:
            return await self.refresh()
        return self._snapshot

    def integration(self, key: str) -> IntegrationState | None:
        return self._snapshot.integrations.get(key)

    def policy(self, key: str) -> dict:
        """El valor vigente: lo guardado sobre los valores por defecto."""
        definicion = policy_defs.BY_KEY[key]
        return {**definicion.defaults(), **self._snapshot.policies.get(key, {})}

    def secret(self, integration_key: str, name: str) -> str | None:
        """Descifra un secreto de la instantánea. `None` si no está guardado."""
        estado = self.integration(integration_key)
        entrada = estado.secrets.get(name) if estado else None
        if entrada is None:
            return None
        return unseal(
            integration_key=integration_key,
            secret_name=name,
            ciphertext=entrada.ciphertext,
            nonce=entrada.nonce,
            stored_key_id=entrada.key_id,
        )


platform_config = PlatformConfig()


async def notify_change(session) -> None:
    """Avisa a las demás instancias. Se entrega al confirmar la transacción."""
    await session.execute(text(f"NOTIFY {CHANNEL}"))


async def listen_for_changes(stop: asyncio.Event) -> None:
    """Escucha los cambios de otras instancias hasta que `stop` se active.

    Es una mejora, no un requisito: si no puede conectar, lo registra y deja que
    `ensure_fresh()` recargue por antigüedad.
    """
    import asyncpg

    from app.database import libpq_dsn

    dsn = libpq_dsn()
    while not stop.is_set():
        conexion = None
        try:
            conexion = await asyncpg.connect(dsn)

            def _al_cambiar(*_args) -> None:
                asyncio.get_running_loop().create_task(platform_config.refresh())

            await conexion.add_listener(CHANNEL, _al_cambiar)
            await stop.wait()
        except Exception:
            logger.warning("PLATFORM | config listener unavailable; retrying in 30s", exc_info=True)
            try:
                await asyncio.wait_for(stop.wait(), timeout=30)
            except TimeoutError:
                pass
        finally:
            if conexion is not None:
                await conexion.close()
