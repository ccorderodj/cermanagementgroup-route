"""
La interfaz de almacenamiento y su adaptador de desarrollo.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from app.config import settings


#: Carpeta del adaptador de desarrollo. Es configurable a propósito: en esta
#: máquina el disco del sistema está lleno, y una ruta fija bajo el perfil del
#: usuario habría hecho que subir un archivo fallara por una razón que no tiene
#: nada que ver con el código.
STORAGE_ROOT_DEV = Path(
    os.environ.get("STORAGE_ROOT")
    or getattr(settings, "STORAGE_ROOT", "")
    or (Path.cwd() / "var" / "storage")
)


class UnsupportedFileType(Exception):
    """El tipo no está en la lista permitida."""


class FileTooLarge(Exception):
    """El archivo pasa del límite configurado."""


@dataclass(frozen=True)
class StorageObject:
    """Lo que el dominio necesita saber de un archivo ya guardado.

    No lleva los bytes: quien lo recibe ya no los necesita, y arrastrarlos por
    la aplicación es la forma más fácil de que acaben en un log.
    """

    storage_key: str
    content_hash: str
    byte_size: int
    content_type: str
    original_filename: str | None


class StorageProvider(Protocol):
    """Lo que la capa de dominio puede pedirle a un almacén.

    Deliberadamente pequeño y sin nada de un proveedor concreto: ni `Bucket`, ni
    rutas de Windows, ni URLs de S3. Cambiar de proveedor tiene que ser escribir
    otra clase, no reescribir el dominio.
    """

    def put(
        self,
        *,
        data: bytes,
        content_type: str,
        original_filename: str | None,
        scope: str,
    ) -> StorageObject:
        """Guarda el archivo y devuelve su clave y su huella."""
        ...

    def open(self, storage_key: str) -> bytes:
        """Devuelve el contenido de un objeto ya autorizado por quien llama."""
        ...

    def exists(self, storage_key: str) -> bool:
        ...

    def delete(self, storage_key: str) -> bool:
        """Retira un objeto. Devuelve si existía.

        Borrar algo que ya no está **no es un error**: dos barridos solapados o
        un reintento llegan a la misma conclusión, y hacer fallar al segundo
        convertiría una carrera inofensiva en ruido. Devuelve `False` y sigue.
        """
        ...

    def put_derivative(self, *, data: bytes, content_type: str, scope: str) -> StorageObject:
        """Guarda un objeto que genera el servidor (miniatura, normalizada)."""
        ...


#: Caracteres que sobreviven al saneado de un nombre. Todo lo demás pasa a `_`.
_NOMBRE_SEGURO = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_filename(nombre: str | None) -> str | None:
    """Deja el nombre original en algo que se pueda enseñar sin miedo.

    Esto **no** hace seguro el destino —de eso se encarga generar la clave en el
    servidor—; hace seguro *mostrar* el nombre y guardarlo como metadato. Se
    quita cualquier rastro de ruta antes de tocar nada más: `..\\..\\x.png` no
    puede quedar como `.._.._x.png` y seguir pareciendo un nombre.
    """
    if not nombre:
        return None
    solo_nombre = nombre.replace("\\", "/").split("/")[-1]
    limpio = _NOMBRE_SEGURO.sub("_", solo_nombre).strip("._")
    return limpio[:255] or None


def build_storage_key(*, scope: str, content_type: str) -> str:
    """La clave de destino. **La decide el servidor, siempre.**

    Lleva fecha para que la carpeta no crezca sin fondo, un ámbito para poder
    localizar lo de un expediente, y un UUID4 para que nadie pueda adivinar ni
    colisionar. Lo que no lleva es una sola letra escrita por quien sube el
    archivo.
    """
    # Se sanea segmento a segmento y se vuelve a unir: saneando la cadena
    # entera, la barra se convertiria en `_` y la clave perderia la jerarquia
    # que permite localizar lo de un expediente.
    segmentos = [
        _NOMBRE_SEGURO.sub("_", parte).strip("._")
        for parte in str(scope).split("/")
        if parte not in ("", ".", "..")
    ]
    ambito = "/".join(p for p in segmentos if p) or "unscoped"
    hoy = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    extension = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/heic": ".heic",
        "image/heif": ".heif",
        "application/pdf": ".pdf",
    }.get(content_type, ".bin")
    return f"{ambito}/{hoy}/{uuid.uuid4().hex}{extension}"


def validate_upload(*, data: bytes, content_type: str) -> str:
    """Tipo permitido, contenido coherente con él, y tamaño dentro del límite.

    Devuelve el tipo **con el que se guarda**, que sale de los bytes: un
    navegador de escritorio manda una foto HEIC como `application/octet-stream`.
    Las firmas y la resolución viven en `app/core/storage/media.py`.

    La lista blanca, el límite y las páginas de un PDF son la política de subida
    de Settings (WP-2), con los valores del entorno como respaldo: cambiarlos no
    exige redesplegar.

    Lo que **no** es configuración es que los bytes se parezcan a lo que dicen
    ser. Antes bastaba con declarar `image/png` para que se guardara cualquier
    cosa, incluido un ejecutable; el tipo declarado lo escribe quien sube el
    archivo, así que creerle sin mirar es creer al cliente.

    Que quede dicho con precisión: esto comprueba el **tipo**, no la
    inocuidad. Un PNG puede ser un PNG y ser malicioso igualmente. El análisis
    de seguridad sigue sin proveedor configurado y sigue diciéndolo; esta
    comprobación no lo sustituye ni permite que nada se declare `CLEAN`.
    """
    from app.core.platform.config_service import platform_config
    from app.core.storage.media import (
        GENERIC_TYPES,
        PDF_TYPE,
        MediaRejected,
        inspect_pdf,
        resolve_content_type,
        same_family,
    )

    politica = platform_config.policy("upload")
    permitidos = {str(t).strip().lower() for t in politica["allowed_types"] if str(t).strip()}

    def _permitido(tipo: str) -> bool:
        return any(same_family(tipo, p) for p in permitidos)

    declarado = (content_type or "").split(";", 1)[0].strip().lower()
    if declarado not in GENERIC_TYPES and not _permitido(declarado):
        raise UnsupportedFileType(
            f"{content_type} is not an accepted document type."
        )

    limite = int(politica["max_bytes"])
    if len(data) > limite:
        raise FileTooLarge(
            f"The file is larger than the {limite} byte limit."
        )
    if not data:
        raise FileTooLarge("The file is empty.")

    # Después del tamaño: un archivo vacío se sigue rechazando por vacío, que es
    # lo que es, y no por no parecerse a un PNG.
    try:
        efectivo = resolve_content_type(data=data, declared=content_type)
        if not _permitido(efectivo):
            raise MediaRejected(f"{efectivo} is not an accepted document type.")
        if efectivo == PDF_TYPE:
            inspect_pdf(data, max_pages=int(politica["max_pdf_pages"]))
    except MediaRejected as exc:
        raise UnsupportedFileType(str(exc)) from exc
    return efectivo


class LocalFileStorage:
    """Adaptador de **desarrollo**. Escribe en una carpeta local.

    No replica, no cifra en reposo, no versiona por sí mismo y no emite URLs
    firmadas. Existe para que el dominio se pueda construir y probar sin un
    proveedor en la nube, y para dejar claro dónde encaja el que se apruebe.

    Que esto sea desarrollo no lo hace descuidado: la clave se genera arriba, y
    aquí se comprueba además que la clave resuelta no se salga de la raíz. Una
    comprobación de más en el sitio donde un error escribe fuera del árbol.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or STORAGE_ROOT_DEV)

    def _ruta(self, storage_key: str) -> Path:
        destino = (self.root / storage_key).resolve()
        raiz = self.root.resolve()
        if raiz != destino and raiz not in destino.parents:
            raise ValueError("The storage key resolves outside the storage root.")
        return destino

    def put(
        self,
        *,
        data: bytes,
        content_type: str,
        original_filename: str | None,
        scope: str,
    ) -> StorageObject:
        efectivo = validate_upload(data=data, content_type=content_type)
        objeto = self.put_derivative(data=data, content_type=efectivo, scope=scope)
        return StorageObject(
            storage_key=objeto.storage_key,
            content_hash=objeto.content_hash,
            byte_size=objeto.byte_size,
            content_type=efectivo,
            original_filename=sanitize_filename(original_filename),
        )

    def put_derivative(self, *, data: bytes, content_type: str, scope: str) -> StorageObject:
        """Escribe un objeto generado por el servidor. Sin validar como subida:
        no lo envió nadie, y la política de tipos admitidos no se le aplica."""
        storage_key = build_storage_key(scope=scope, content_type=content_type)
        destino = self._ruta(storage_key)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(data)
        return StorageObject(
            storage_key=storage_key,
            content_hash=hashlib.sha256(data).hexdigest(),
            byte_size=len(data),
            content_type=content_type,
            original_filename=None,
        )

    def open(self, storage_key: str) -> bytes:
        return self._ruta(storage_key).read_bytes()

    def delete(self, storage_key: str) -> bool:
        destino = self._ruta(storage_key)
        try:
            destino.unlink()
        except FileNotFoundError:
            return False
        # Se limpian los directorios de fecha que quedan vacíos. Sin esto el
        # almacén acumula un árbol de carpetas huecas, una por día, que nadie
        # mira hasta que estorban.
        padre = destino.parent
        raiz = self.root.resolve()
        while padre != raiz and padre.is_relative_to(raiz):
            try:
                padre.rmdir()
            except OSError:
                break
            padre = padre.parent
        return True

    def exists(self, storage_key: str) -> bool:
        try:
            return self._ruta(storage_key).is_file()
        except ValueError:
            return False


class S3CompatibleStorage:
    """Almacén de **producción**: DigitalOcean Spaces, AWS S3 o compatible.

    Varias instancias de la aplicación ven los mismos documentos, que es lo que
    el almacén local no podía garantizar.

    La clave la sigue generando el servidor (`build_storage_key`), con el
    prefijo configurado delante. `open` y `exists` usan la clave tal como está
    guardada, así que los documentos migrados desde el almacén local conservan
    la suya: la base no se reescribe al cambiar de proveedor.
    """

    name = "s3_compatible"

    def __init__(
        self,
        *,
        endpoint: str | None,
        region: str | None,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        prefix: str = "",
        client=None,
    ) -> None:
        self.endpoint = endpoint
        self.region = region or None
        self.bucket = bucket
        self.prefix = (prefix or "").lstrip("/")
        if client is None:
            import boto3
            from botocore.config import Config

            client = boto3.client(
                "s3",
                endpoint_url=endpoint or None,
                region_name=self.region,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                config=Config(
                    signature_version="s3v4",
                    retries={"max_attempts": 3, "mode": "standard"},
                    connect_timeout=10,
                    read_timeout=30,
                ),
            )
        self._client = client

    def put(
        self,
        *,
        data: bytes,
        content_type: str,
        original_filename: str | None,
        scope: str,
    ) -> StorageObject:
        efectivo = validate_upload(data=data, content_type=content_type)
        objeto = self.put_derivative(data=data, content_type=efectivo, scope=scope)
        return StorageObject(
            storage_key=objeto.storage_key,
            content_hash=objeto.content_hash,
            byte_size=objeto.byte_size,
            content_type=efectivo,
            original_filename=sanitize_filename(original_filename),
        )

    def put_derivative(self, *, data: bytes, content_type: str, scope: str) -> StorageObject:
        """Escribe un objeto generado por el servidor, sin validarlo como subida."""
        storage_key = f"{self.prefix}{build_storage_key(scope=scope, content_type=content_type)}"
        self.put_existing(storage_key=storage_key, data=data, content_type=content_type)
        return StorageObject(
            storage_key=storage_key,
            content_hash=hashlib.sha256(data).hexdigest(),
            byte_size=len(data),
            content_type=content_type,
            original_filename=None,
        )

    def put_existing(self, *, storage_key: str, data: bytes, content_type: str) -> None:
        """Escribe con una clave ya decidida. Lo usa la migración desde el local."""
        self._client.put_object(
            Bucket=self.bucket,
            Key=storage_key,
            Body=data,
            ContentType=content_type,
            Metadata={"sha256": hashlib.sha256(data).hexdigest()},
        )

    def open(self, storage_key: str) -> bytes:
        return self._client.get_object(Bucket=self.bucket, Key=storage_key)["Body"].read()

    def delete(self, storage_key: str) -> bool:
        # S3 no distingue borrar lo que estaba de borrar lo que no: `delete_object`
        # responde igual. Se consulta antes para poder contar lo que de verdad se
        # retiró, que es lo que hace legible el informe del barrido.
        existia = self.exists(storage_key)
        self._client.delete_object(Bucket=self.bucket, Key=storage_key)
        return existia

    def exists(self, storage_key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self.bucket, Key=storage_key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
        return True

    def probe_key(self) -> str:
        import uuid

        return f"{self.prefix}.healthcheck/{uuid.uuid4().hex}.tmp"

    def delete_probe(self, storage_key: str) -> None:
        """Sólo para la sonda de salud. La evidencia no se borra."""
        if not storage_key.startswith(f"{self.prefix}.healthcheck/"):
            raise ValueError("Only health-check probe objects can be deleted.")
        self._client.delete_object(Bucket=self.bucket, Key=storage_key)

    def is_publicly_readable(self, storage_key: str) -> bool:
        """Si alguien **sin credenciales** puede leer el objeto.

        Archivos privados en un bucket público serían una filtración. La sonda de
        salud lo comprueba con una petición sin firmar.
        """
        import boto3
        from botocore import UNSIGNED
        from botocore.config import Config
        from botocore.exceptions import ClientError

        anonimo = boto3.client(
            "s3",
            endpoint_url=self.endpoint or None,
            region_name=self.region,
            config=Config(signature_version=UNSIGNED, connect_timeout=10, read_timeout=10),
        )
        try:
            anonimo.get_object(Bucket=self.bucket, Key=storage_key)
        except ClientError:
            return False
        return True


def get_storage() -> StorageProvider:
    """El almacén en uso: el configurado en Settings o, si no hay, el local.

    Si Settings dice S3 pero su credencial no se puede descifrar, esto **falla**
    en vez de caer al disco local: guardar evidencia en un sitio distinto del
    configurado sería perderla para las demás instancias sin que nadie lo note.
    """
    from app.core.platform.config_service import platform_config

    estado = platform_config.integration("document_storage")
    if estado is not None and estado.enabled:
        c = estado.config
        if estado.provider == "s3_compatible":
            secreto = platform_config.secret("document_storage", "secret_access_key")
            if secreto:
                return S3CompatibleStorage(
                    endpoint=c.get("endpoint"),
                    region=c.get("region"),
                    bucket=c["bucket"],
                    access_key_id=c["access_key_id"],
                    secret_access_key=secreto,
                    prefix=c.get("prefix", ""),
                )
        if estado.provider == "local" and c.get("root"):
            return LocalFileStorage(Path(c["root"]))
    return LocalFileStorage()
