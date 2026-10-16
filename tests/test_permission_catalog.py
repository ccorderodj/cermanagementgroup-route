"""
Coherencia entre el catálogo de capacidades y lo que el código exige.

Por qué existe este test
------------------------
Los nombres de permiso eran literales repetidos en dos listas sin relación: el
catálogo del bootstrap y las llamadas a `require_permissions([...])` en los
routers. Ya divergieron una vez: `regions.update` estaba en el código pero nunca
se sembró, así que los dos endpoints que lo exigían devolvían 403 a **todos** los
roles, `admin` incluido, y la pantalla de estados de operación era de solo
lectura para cualquiera que no fuera administrador de plataforma. Nadie lo notó
(AUD-DB-001).

Se comprueba en las **dos direcciones**:

* Ningún endpoint puede exigir una capacidad que no esté en el catálogo —sería
  un 403 permanente que ningún rol puede resolver.
* Ninguna capacidad del catálogo puede sobrar —concede autoridad nominal sobre
  algo que no existe, que es cómo se acumulan permisos fantasma (AUD-SEC-014).

No necesita base de datos: lee el código fuente.
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path

from app.core.rbac.catalog import CAPABILITY_NAMES, DEFAULT_ROLES, capabilities_for


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "app"
REACT_ROOT = REPO_ROOT / "app" / "components" / "react"


def _string_list(node: ast.AST) -> list[str] | None:
    """Extrae `['a.b', 'c.d']` de un nodo del AST, si es una lista literal."""
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    values = []
    for element in node.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            values.append(element.value)
        else:
            return None
    return values


# Directorios en los que no hay código de la aplicación. Se podan **durante**
# el recorrido, no después: `app/node_modules` tiene 6.832 directorios y 51.622
# ficheros, y `rglob` desciende a todos ellos antes de que un filtro sobre
# `path.parts` pueda descartarlos. Medido: 2.513 ms descendiendo contra 166 ms
# podando, para los mismos 205 ficheros de la aplicación.
#
# Y no es sólo tiempo. `app/node_modules` contiene hoy dos ficheros `.py`
# (`flatted/python/flatted.py` y `shell-quote/print.py`) que este test estaba
# parseando con `ast`. Hoy los dos parsean y ninguno menciona una capacidad, así
# que no fallaba nada; pero qué se parsea dependía de qué paquetes npm hubiera
# instalados, y bastaba una dependencia nueva con un `.py` de Python 2 para que
# `ast.parse` levantara un `SyntaxError` sin relación con el producto.
DIRECTORIOS_AJENOS = frozenset(
    {"node_modules", "components", "migrations", "__pycache__", ".venv"}
)


def _fuentes_del_backend() -> list[Path]:
    """Los `.py` de la aplicación, sin descender a lo que no es suyo."""
    encontrados: list[Path] = []
    pendientes = [BACKEND_ROOT]

    while pendientes:
        for entrada in pendientes.pop().iterdir():
            if entrada.is_dir():
                if entrada.name not in DIRECTORIOS_AJENOS:
                    pendientes.append(entrada)
            elif entrada.suffix == ".py":
                encontrados.append(entrada)

    return encontrados


@lru_cache(maxsize=1)
def permissions_required_by_backend() -> dict[str, list[str]]:
    """Capacidades que exige cada archivo, leyendo el AST.

    Se usa el AST y no una expresión regular porque una regexp no distingue una
    llamada real de una mención en un comentario o en una cadena de texto.

    El resultado se cachea porque dos tests lo piden y el árbol de fuentes no
    cambia durante una ejecución: leerlo dos veces era repetir un cálculo cuyo
    resultado ya se tenía. Lo que devuelve no se muta en ningún sitio.
    """
    found: dict[str, list[str]] = {}

    for path in _fuentes_del_backend():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            callee = node.func
            name = getattr(callee, "id", None) or getattr(callee, "attr", None)
            if name not in {
                "require_permissions",
                "require_page_permissions",
                # `has_permissions` no corta la peticion: informa de si el
                # usuario puede ver un campo concreto (la tarifa de facturacion
                # de un perfil de puesto). Sigue siendo una capacidad exigida
                # por el servidor, asi que cuenta igual en las dos direcciones.
                "has_permissions",
            }:
                continue

            if not node.args:
                continue

            values = _string_list(node.args[0])
            assert values is not None, (
                f"{path}: {name}() debe recibir una lista literal de cadenas "
                "para que este test pueda comprobarla."
            )
            found.setdefault(str(path.relative_to(REPO_ROOT)), []).extend(values)

    return found


def permissions_used_by_frontend() -> set[str]:
    """Capacidades que el frontend comprueba (`hasUserPermission('x.y')`)."""
    used: set[str] = set()
    pattern = re.compile(
        r"(?:hasUserPermission|hasAnyUserPermission|requiredPermission:)\s*[(:]?\s*'([a-z]+\.[a-z]+)'"
    )

    for path in REACT_ROOT.rglob("*.ts*"):
        used.update(pattern.findall(path.read_text(encoding="utf-8")))

    return used


# ── Comprobaciones ──────────────────────────────────────────────────────────


def test_backend_only_requires_capabilities_that_exist_in_the_catalog():
    by_file = permissions_required_by_backend()

    unknown: dict[str, list[str]] = {}
    for file_name, permissions in by_file.items():
        missing = sorted(set(permissions) - CAPABILITY_NAMES)
        if missing:
            unknown[file_name] = missing

    assert not unknown, (
        "Estos endpoints exigen capacidades que no están en "
        "app/core/rbac/catalog.py. Ningún rol puede tenerlas, así que "
        f"devolverán 403 para siempre:\n{unknown}"
    )


def test_every_catalog_capability_is_required_somewhere():
    required = {
        permission
        for permissions in permissions_required_by_backend().values()
        for permission in permissions
    }

    unused = sorted(CAPABILITY_NAMES - required)
    assert not unused, (
        "Estas capacidades están en el catálogo y ningún endpoint las exige. "
        "Conceden autoridad sobre algo que no existe, y quien las asigne creerá "
        f"haber dado un permiso que no hace nada:\n{unused}"
    )


def test_frontend_only_checks_capabilities_that_exist():
    unknown = sorted(permissions_used_by_frontend() - CAPABILITY_NAMES)
    assert not unknown, (
        "El frontend comprueba capacidades que no están en el catálogo. "
        "Ocultaría elementos que nadie puede desbloquear nunca: "
        f"{unknown}"
    )


def test_default_roles_only_grant_capabilities_that_exist():
    for template in DEFAULT_ROLES:
        unknown = sorted(set(capabilities_for(template)) - CAPABILITY_NAMES)
        assert not unknown, (
            f"El rol por defecto '{template.name}' concede capacidades que no "
            f"están en el catálogo: {unknown}"
        )


def test_default_roles_have_a_valid_category():
    """La categoría decide quién puede aprobar cambios de permisos.

    Un valor fuera de los dos admitidos dejaría al rol sin autoridad de revisión
    sin que nada lo indicara. La base lo impide con un CHECK; aquí se comprueba
    que las plantillas tampoco lo intenten.
    """
    for template in DEFAULT_ROLES:
        assert template.category in {"management", "operative"}, (
            f"El rol '{template.name}' tiene la categoría '{template.category}', "
            "que no es ni 'management' ni 'operative'."
        )


def test_at_least_one_default_role_can_review_permission_changes():
    """Sin un rol de gestión, nadie podría aprobar un cambio de permisos.

    Una compañía nueva quedaría con el maker-checker bloqueado: se podrían
    enviar solicitudes y no resolverlas.
    """
    management = [t for t in DEFAULT_ROLES if t.category == "management"]
    assert management, (
        "Ninguno de los roles por defecto es de categoría 'management': una "
        "compañía nueva no tendría a nadie que pudiera aprobar cambios de "
        "capacidades."
    )


def test_superuser_is_not_a_capability():
    """`is_superuser` es privilegio de plataforma, no un permiso de tenant (D6).

    Si apareciera en el catálogo podría concederse a un rol, y con ello
    cualquier administrador de tenant tendría acceso a todos los tenants.
    """
    suspicious = sorted(
        name for name in CAPABILITY_NAMES
        if "superuser" in name or "platform" in name
    )
    assert not suspicious, (
        "El catálogo no debe contener capacidades de plataforma: se concederían "
        f"desde la administración de un tenant. {suspicious}"
    )
