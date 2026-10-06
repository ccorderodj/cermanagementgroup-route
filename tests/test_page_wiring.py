"""
Coherencia del cableado de páginas (patrón server-route + page-key).

Por qué existe este test
------------------------
Una misma cadena tiene que aparecer idéntica en cuatro sitios:

    name= de la ruta FastAPI
      -> request.state.url_name
      -> data-current-page en la plantilla Jinja
      -> valor del enum ComponentRoot
      -> clave de RootComponents

Si uno de ellos discrepa, **la página se queda en blanco sin lanzar ningún
error**. Es el modo de fallo más insidioso del sistema: no hay excepción, no hay
log, no hay 500. Solo una pantalla vacía.

Hasta ahora las cuatro listas se mantenían a mano, con una lista de comprobación
en la documentación y ninguna verificación automática (AUD-TOOL-008). Con cada
pantalla nueva que construya un dominio, la probabilidad de que alguna se desajuste
tiende a uno.

No necesita base de datos: es introspección de las rutas registradas más lectura
de los archivos del frontend.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
REACT_ROOT = REPO_ROOT / "app" / "components" / "react"
TEMPLATES_ROOT = REPO_ROOT / "app" / "templates"

MAINCONTENT_ENUM = REACT_ROOT / "app/providers/maincontent/ui/maincontent.ts"
MAINCONTENT_MAP = REACT_ROOT / "app/providers/maincontent/config/mainContentConfig.tsx"
PAGES_DIR = REACT_ROOT / "pages"


# ── Recolección de cada fuente ──────────────────────────────────────────────


def fastapi_page_names() -> set[str]:
    """Los `name=` de las rutas de página, tal y como están registradas."""
    from app.main import frontend

    names: set[str] = set()

    def walk(routes) -> None:
        for route in routes:
            if type(route).__name__ == "_IncludedRouter":
                walk(route.original_router.routes)
                continue
            name = getattr(route, "name", None)
            methods = getattr(route, "methods", None) or set()
            # Los mounts (estáticos) no son páginas.
            if name and "GET" in methods and type(route).__name__ != "Mount":
                names.add(name)

    walk(frontend.routes)
    return names


def component_root_values() -> set[str]:
    """Valores del enum `ComponentRoot`."""
    source = MAINCONTENT_ENUM.read_text(encoding="utf-8")
    return set(re.findall(r"=\s*'([A-Za-z0-9_]+)'", source))


def root_components_keys() -> set[str]:
    """Claves del mapa `RootComponents`, resueltas a través del enum.

    Las entradas se escriben como `[ComponentRoot.LOGIN]: <LoginPage />`, así
    que hay que traducir el miembro del enum a su valor.
    """
    enum_source = MAINCONTENT_ENUM.read_text(encoding="utf-8")
    members = dict(re.findall(r"([A-Z0-9_]+)\s*=\s*'([A-Za-z0-9_]+)'", enum_source))

    map_source = MAINCONTENT_MAP.read_text(encoding="utf-8")
    used = re.findall(r"\[ComponentRoot\.([A-Z0-9_]+)\]\s*:", map_source)

    unknown = [member for member in used if member not in members]
    assert not unknown, (
        f"RootComponents usa miembros que no existen en ComponentRoot: {unknown}"
    )

    return {members[member] for member in used}


def template_page_keys() -> set[str]:
    """Nombres de ruta que las plantillas esperan recibir en `url_name`.

    Una plantilla no dice qué clave usa —la recibe del servidor— así que lo que
    se comprueba es que **imprima el atributo**. Sin él, React no encuentra el
    ancla y no monta nada.
    """
    templates_with_anchor: set[Path] = set()
    for path in TEMPLATES_ROOT.rglob("*.html"):
        source = path.read_text(encoding="utf-8")
        if "rc-currentPage" in source:
            templates_with_anchor.add(path)
    return templates_with_anchor


def page_directories() -> set[str]:
    return {
        entry.name
        for entry in PAGES_DIR.iterdir()
        if entry.is_dir() and (entry / "index.ts").exists()
    }


# ── Comprobaciones ──────────────────────────────────────────────────────────


def test_every_fastapi_page_has_a_component_root_value():
    routes = fastapi_page_names()
    enum_values = component_root_values()

    missing = routes - enum_values
    assert not missing, (
        "Estas rutas de página tienen name= pero no hay un valor igual en el "
        f"enum ComponentRoot, así que la página saldrá en blanco: {sorted(missing)}"
    )


def test_every_component_root_value_has_a_fastapi_route():
    routes = fastapi_page_names()
    enum_values = component_root_values()

    orphan = enum_values - routes
    assert not orphan, (
        "Estos valores de ComponentRoot no corresponden a ninguna ruta FastAPI "
        f"registrada: {sorted(orphan)}"
    )


def test_every_component_root_value_is_mapped_to_a_component():
    enum_values = component_root_values()
    mapped = root_components_keys()

    missing = enum_values - mapped
    assert not missing, (
        "Estas claves están en ComponentRoot pero no en RootComponents. "
        "AppMainContent no encontrará componente y la página quedará vacía: "
        f"{sorted(missing)}"
    )


def test_root_components_has_no_entries_without_enum_value():
    enum_values = component_root_values()
    mapped = root_components_keys()

    extra = mapped - enum_values
    assert not extra, (
        f"RootComponents mapea claves que ya no están en ComponentRoot: {sorted(extra)}"
    )


def test_page_directories_match_the_registered_pages():
    routes = fastapi_page_names()
    directories = page_directories()

    missing = routes - directories
    assert not missing, (
        "No hay carpeta en pages/ para estas rutas: " f"{sorted(missing)}"
    )

    orphan = directories - routes
    assert not orphan, (
        "Estas carpetas de pages/ no corresponden a ninguna ruta de página. "
        "Si son intencionadas, hay que registrarles su ruta; si no, sobran: "
        f"{sorted(orphan)}"
    )


PAGE_TEMPLATES = [
    "login.html",
    "password-reset.html",
    "change-password.html",
    "admin/index.html",
    "profile/index.html",
    "admin/companies/list.html",
    "admin/companies/profile.html",
    "admin/locations/states.html",
    "admin/security/users/list.html",
    "admin/security/roles/list.html",
    "admin/security/permissions/list.html",
    "admin/security/rolepermissionrequests/list.html",
    "admin/platform/settings.html",
    "admin/platform/diagnostics.html",
    # CER Route: configuración en el shell de administración.
    "admin/route/users.html",
    "admin/route/supervisors.html",
    "admin/route/vehicles.html",
    "admin/route/standard-values.html",
    "admin/route/today-live.html",
    "admin/route/activity.html",
    "admin/route/odometer-exceptions.html",
    # CER Route: espacio móvil del supervisor.
    "route/my-route.html",
    "route/activity.html",
    "route/me.html",
]


@pytest.mark.parametrize("template_name", PAGE_TEMPLATES)
def test_page_templates_print_the_page_key_anchor(template_name: str):
    """El ancla debe existir y llevar el valor **entre comillas**.

    Sin comillas funcionaba de milagro: todos los `name=` actuales son
    identificadores sin espacios. Uno con un espacio —`Job Opening Register`—
    rompería el HTML en silencio (AUD-FE-007).
    """
    source = (TEMPLATES_ROOT / template_name).read_text(encoding="utf-8")

    assert 'id="rc-currentPage"' in source, (
        f"{template_name} no imprime el ancla #rc-currentPage: React no sabrá "
        "qué página montar."
    )
    assert 'data-current-page="{{ url_name }}"' in source, (
        f"{template_name} debe imprimir data-current-page entrecomillado."
    )


def test_the_four_sources_have_the_same_size():
    """Comprobación redundante a propósito: si algo se desajusta, este falla primero."""
    routes = fastapi_page_names()
    enum_values = component_root_values()
    mapped = root_components_keys()
    directories = page_directories()

    assert len(routes) == len(enum_values) == len(mapped) == len(directories), (
        "Las cuatro fuentes del page-key no tienen el mismo número de entradas:\n"
        f"  rutas FastAPI  : {len(routes)}  {sorted(routes)}\n"
        f"  ComponentRoot  : {len(enum_values)}  {sorted(enum_values)}\n"
        f"  RootComponents : {len(mapped)}  {sorted(mapped)}\n"
        f"  pages/         : {len(directories)}  {sorted(directories)}"
    )


# ── Cadena completa por página retenida ────────────────────────────────────


#: Plantillas que no son páginas de React: el esqueleto y los errores.
NON_PAGE_TEMPLATES = {"base.html", "403.html", "404.html"}


def test_every_page_template_is_covered_by_the_anchor_test():
    """Toda plantilla de página nueva entra en la lista de arriba, o este test falla."""
    en_disco = {
        str(f.relative_to(TEMPLATES_ROOT)).replace("\\", "/")
        for f in TEMPLATES_ROOT.rglob("*.html")
    } - NON_PAGE_TEMPLATES
    parametrizadas = set(PAGE_TEMPLATES)
    assert en_disco == parametrizadas, (
        f"sin test de ancla: {sorted(en_disco - parametrizadas)}; "
        f"en la lista pero sin archivo: {sorted(parametrizadas - en_disco)}"
    )


def test_every_retained_page_key_resolves_to_a_component_file():
    """ruta FastAPI → ComponentRoot → RootComponents → pages/<Key>/ui/<Key>.tsx."""
    for clave in sorted(fastapi_page_names()):
        assert clave in component_root_values(), f"{clave}: no está en ComponentRoot"
        assert clave in root_components_keys(), f"{clave}: no está en RootComponents"
        componente = PAGES_DIR / clave / "ui" / f"{clave}.tsx"
        assert componente.is_file(), f"{clave}: falta {componente.relative_to(REPO_ROOT)}"


def test_the_store_is_not_persisted():
    """El estado de Redux no se persiste.

    Lleva datos del tenant y del usuario; persistirlo los dejaría en el
    almacenamiento del navegador sin que nadie lo hubiera decidido.
    """
    raiz = REACT_ROOT / "app/providers/StoreProvider"
    for f in raiz.rglob("*.ts*"):
        texto = f.read_text(encoding="utf-8")
        assert "redux-persist" not in texto, f"{f.name} persiste el store"
