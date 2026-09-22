"""
Rota la llave maestra: re-cifra cada credencial con la llave actual.

Procedimiento
-------------
1. Generar una llave nueva: ``python -m app.core.platform.secrets generate``.
2. En el entorno del despliegue: ``PLATFORM_MASTER_KEY=<nueva>`` y
   ``PLATFORM_MASTER_KEY_PREVIOUS=<anterior>``. Reiniciar.
3. Ejecutar este comando. Re-cifra lo que siga con la anterior.
4. Quitar ``PLATFORM_MASTER_KEY_PREVIOUS`` y reiniciar.

Entre el paso 2 y el 3 todo sigue funcionando: el descifrado acepta las dos
llaves. Si falta la anterior, el comando se detiene sin tocar nada, porque
re-cifrar exige poder descifrar primero.

    .venv/Scripts/python.exe -m app.core.platform.rotate_master_key
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import select

from app.core.platform.audit import REDACTED, record_platform_event
from app.core.platform.secrets import current_key_id, seal, unseal
from app.database import async_session_maker
from app.db.model_registry import load_all_models

load_all_models()


@dataclass
class RotationReport:
    rotated: int = 0
    already_current: int = 0


async def rotate() -> RotationReport:
    from app.core.platform.models import PlatformIntegration, PlatformSecret

    actual = current_key_id()
    if actual is None:
        raise SystemExit("PLATFORM_MASTER_KEY is not configured.")

    informe = RotationReport()
    async with async_session_maker() as session:
        filas = (
            await session.execute(
                select(PlatformSecret, PlatformIntegration.key)
                .join(PlatformIntegration, PlatformIntegration.id == PlatformSecret.integration_id)
                .with_for_update()
            )
        ).all()

        # Primero se comprueba que todo descifra. Re-cifrar la mitad y fallar en
        # la otra mitad dejaría dos llaves necesarias para siempre.
        claros = []
        for secreto, integracion in filas:
            if secreto.key_id == actual:
                informe.already_current += 1
                continue
            claros.append(
                (
                    secreto,
                    integracion,
                    unseal(
                        integration_key=integracion,
                        secret_name=secreto.name,
                        ciphertext=bytes(secreto.ciphertext),
                        nonce=bytes(secreto.nonce),
                        stored_key_id=secreto.key_id,
                    ),
                )
            )

        for secreto, integracion, claro in claros:
            sellado = seal(integration_key=integracion, secret_name=secreto.name, plaintext=claro)
            secreto.ciphertext = sellado.ciphertext
            secreto.nonce = sellado.nonce
            secreto.key_id = sellado.key_id
            informe.rotated += 1

        await session.commit()

    if informe.rotated:
        await record_platform_event(
            request=None,
            actor=None,
            action="master_key.rotated",
            target="platform:master_key",
            changes={"rotated": informe.rotated, "key_id": actual, "values": REDACTED},
        )
    return informe


if __name__ == "__main__":
    resultado = asyncio.run(rotate())
    print(f"re-cifradas: {resultado.rotated} · ya con la llave actual: {resultado.already_current}")
