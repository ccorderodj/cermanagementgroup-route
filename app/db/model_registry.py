"""
Carga todos los modelos de la aplicación.

Por qué hace falta
------------------
SQLAlchemy resuelve las relaciones y las claves foráneas **por nombre**, contra
lo que esté registrado en ese momento. Dentro de la aplicación eso nunca falla,
porque arrancarla importa todos los routers y con ellos todos los modelos.

Un script que se ejecuta solo, en cambio, sólo registra lo que importa. Un
script que importa `company` falla porque `CompanyState` apunta a `Region`. Añadir imports uno a uno es perseguir la siguiente dependencia, así
que se cargan todos, igual que hace la aplicación.
"""

from __future__ import annotations

import importlib
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]

#: Dónde viven los modelos. No se recorre `app/` entero: debajo está el
#: `node_modules` del frontend, y buscar ahí cuesta segundos y no encuentra nada.
_PAQUETES = ("routers_api", "core")


def load_all_models() -> list[str]:
    """Importa cada `models.py` y devuelve los módulos cargados."""
    cargados: list[str] = []
    for paquete in _PAQUETES:
        for fichero in sorted((_RAIZ / paquete).rglob("models.py")):
            relativo = fichero.relative_to(_RAIZ.parent).with_suffix("")
            modulo = ".".join(relativo.parts)
            importlib.import_module(modulo)
            cargados.append(modulo)
    return cargados
