"""
Copia los archivos del almacén local al bucket configurado en Settings.

Qué archivos: los que declare cada módulo de dominio en `STORED_OBJECT_SOURCES`
(una función async que devuelve `StoredObject` desde sus tablas). La base no
guarda archivos propios, así que la lista empieza vacía.

Reglas
------
* **La clave no cambia.** Cada objeto se escribe con la `storage_key` que ya
  tiene en la base, así que ningún registro que la referencia se reescribe.
* **Se verifica la huella antes de copiar.** Un archivo local cuyo SHA-256 no
  coincide con el guardado no se sube: no es la evidencia que se registró, y
  copiarlo la haría pasar por buena.
* **Idempotente.** Lo que ya está en el bucket no se vuelve a subir.
* **En seco por defecto.**

    .venv/Scripts/python.exe -m app.core.storage.migrate_local_to_s3          # en seco
    .venv/Scripts/python.exe -m app.core.storage.migrate_local_to_s3 --apply
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from app.core.storage.base import LocalFileStorage, S3CompatibleStorage, get_storage
from app.db.model_registry import load_all_models

load_all_models()


@dataclass(frozen=True)
class StoredObject:
    storage_key: str
    content_hash: str
    content_type: str


@dataclass
class MigrationReport:
    copied: list[str] = field(default_factory=list)
    already_present: list[str] = field(default_factory=list)
    missing_locally: list[str] = field(default_factory=list)
    hash_mismatch: list[str] = field(default_factory=list)


def migrate_objects(
    objects: list[StoredObject],
    *,
    source: LocalFileStorage,
    target: S3CompatibleStorage,
    apply: bool,
) -> MigrationReport:
    informe = MigrationReport()
    for objeto in objects:
        if target.exists(objeto.storage_key):
            informe.already_present.append(objeto.storage_key)
            continue
        if not source.exists(objeto.storage_key):
            informe.missing_locally.append(objeto.storage_key)
            continue
        datos = source.open(objeto.storage_key)
        if hashlib.sha256(datos).hexdigest() != objeto.content_hash:
            informe.hash_mismatch.append(objeto.storage_key)
            continue
        if apply:
            target.put_existing(
                storage_key=objeto.storage_key, data=datos, content_type=objeto.content_type
            )
        informe.copied.append(objeto.storage_key)
    return informe


#: Fuentes de objetos almacenados. Cada módulo de dominio que guarde archivos
#: registra aquí una función `async () -> list[StoredObject]`.
STORED_OBJECT_SOURCES: list[Callable[[], Awaitable[list[StoredObject]]]] = []


async def _stored_objects() -> list[StoredObject]:
    objetos: list[StoredObject] = []
    for fuente in STORED_OBJECT_SOURCES:
        objetos.extend(await fuente())
    return objetos


def main() -> None:
    from app.core.platform.config_service import platform_config

    parser = argparse.ArgumentParser(description="Copy locally stored files to the configured bucket.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    asyncio.run(platform_config.refresh())
    destino = get_storage()
    if not isinstance(destino, S3CompatibleStorage):
        raise SystemExit("Configure Document storage as S3-compatible in Settings first.")

    informe = migrate_objects(
        asyncio.run(_stored_objects()), source=LocalFileStorage(), target=destino, apply=args.apply
    )
    verbo = "copiados" if args.apply else "se copiarían"
    print(f"{verbo:22}: {len(informe.copied)}")
    print(f"{'ya en el bucket':22}: {len(informe.already_present)}")
    print(f"{'no están en local':22}: {len(informe.missing_locally)}")
    print(f"{'huella distinta':22}: {len(informe.hash_mismatch)} (no se suben)")


if __name__ == "__main__":
    main()
