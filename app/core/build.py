"""
Identificador del build del frontend y cómo se sirve el bundle.

Por qué existe
--------------
El bundle se llama siempre igual (`main.js`, `css/main.css`) y el buildpack de
App Platform deja todos los archivos con fecha de 1980. Sin `Cache-Control`, el
navegador calcula una frescura heurística del 10 % de esa antigüedad —años— y
reutiliza el `main.js` viejo sin preguntar. Revalidar tampoco bastaría: el
`ETag` de Starlette sale de `mtime` y tamaño, así que un build nuevo del mismo
tamaño recibiría un 304.

Lo que se hace
--------------
* La plantilla pide `main.js?v=<build>`: la URL cambia con el contenido.
* Los chunks llevan `[contenthash]` en el nombre y se sirven `immutable`; todo
  lo demás, `no-cache`.
* Cada respuesta estática lleva `X-CER-Build`, que es lo que consulta una
  pestaña que llevaba tiempo abierta para saber si hay versión nueva.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from fastapi.staticfiles import StaticFiles

BUNDLE = Path("app/static/javascript")
_ENTRADAS = ("main.js", "css/main.css")

#: Nombre con hash de contenido de webpack: `140.3f9a…e1.js`.
_CON_HASH = re.compile(r"\.[0-9a-f]{16,}\.(js|css)$")
INMUTABLE = "public, max-age=31536000, immutable"
REVALIDAR = "no-cache"
CABECERA_BUILD = "X-CER-Build"

_calculados: dict[Path, tuple[tuple, str]] = {}


def build_id(directorio: Path = BUNDLE) -> str:
    """Hash corto del contenido de las entradas del bundle.

    Se recalcula sólo si cambia algún archivo (en desarrollo, `webpack --watch`);
    en producción el bundle no cambia mientras el proceso vive.
    """
    firma = tuple(_firma(directorio / nombre) for nombre in _ENTRADAS)
    guardado = _calculados.get(directorio)
    if guardado and guardado[0] == firma:
        return guardado[1]
    resumen = hashlib.sha256()
    for nombre in _ENTRADAS:
        ruta = directorio / nombre
        resumen.update(ruta.read_bytes() if ruta.is_file() else b"-")
    valor = resumen.hexdigest()[:12]
    _calculados[directorio] = (firma, valor)
    return valor


def _firma(ruta: Path) -> tuple[int, int] | None:
    try:
        datos = ruta.stat()
    except FileNotFoundError:
        return None
    return datos.st_mtime_ns, datos.st_size


class StaticConBuild(StaticFiles):
    """`StaticFiles` con caché explícita y el build en cada respuesta."""

    def __init__(self, *args, bundle: Path = BUNDLE, **kwargs):
        super().__init__(*args, **kwargs)
        self._bundle = bundle

    def file_response(self, full_path: str | os.PathLike[str], *args, **kwargs):
        respuesta = super().file_response(full_path, *args, **kwargs)
        respuesta.headers["Cache-Control"] = INMUTABLE if _CON_HASH.search(str(full_path)) else REVALIDAR
        respuesta.headers[CABECERA_BUILD] = build_id(self._bundle)
        return respuesta
