"""
Almacenamiento de archivos y frontera del análisis de malware.

Dos decisiones que conviene decir en voz alta.

**Los bytes no van a PostgreSQL.** La base guarda metadatos —tipo, tamaño,
huella, clave— y el archivo vive en un almacén aparte. Meter documentos de
identidad en una columna habría hinchado copias de seguridad, replicación y
consultas para siempre.

**La clave la genera el servidor.** Si el destino se derivara del nombre que
envía quien sube el archivo, `../../algo` sería una ruta válida y el nombre del
archivo decidiría dónde escribe el servidor. El nombre original se conserva
saneado, como metadato, porque sirve para reconocerlo; no para localizarlo.

Qué es y qué no es este adaptador
---------------------------------
El adaptador de disco es **de desarrollo**. Escribe en una carpeta local
configurable. No es almacenamiento productivo: no replica, no cifra, no versiona
por sí mismo y no da URLs firmadas. El proveedor real sigue siendo decisión
abierta del requisito, y por eso la capa de dominio habla con la interfaz y no
con el disco.
"""

from app.core.storage.base import (
    STORAGE_ROOT_DEV,
    FileTooLarge,
    LocalFileStorage,
    StorageObject,
    StorageProvider,
    UnsupportedFileType,
    get_storage,
    sanitize_filename,
)
from app.core.storage.scanning import (
    NotConfiguredScanner,
    ScanOutcome,
    ScanVerdict,
    get_scanner,
)

__all__ = [
    "STORAGE_ROOT_DEV",
    "FileTooLarge",
    "LocalFileStorage",
    "NotConfiguredScanner",
    "ScanOutcome",
    "ScanVerdict",
    "StorageObject",
    "StorageProvider",
    "UnsupportedFileType",
    "get_scanner",
    "get_storage",
    "sanitize_filename",
]
