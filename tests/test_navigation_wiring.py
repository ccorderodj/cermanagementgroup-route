"""
Coherencia de la navegación entre pantallas.

Por qué existe este test
------------------------
`test_page_wiring.py` comprueba que cada página **existe** en los cuatro sitios
que tienen que decir lo mismo. Lo que no comprobaba nadie es lo contrario: que
cada enlace que una pantalla ofrece **lleve a alguna parte**.

Sin router de frontend, un enlace interno es una cadena escrita a mano dentro de
un `href`. Si la ruta cambia de forma —o si alguien la escribe con una errata—
el enlace no falla al compilar, no lanza ningún error y no aparece en ningún
log: lleva a un 404 en el navegador de quien lo pulse. Es el mismo modo de
fallo silencioso que los tres defectos de frontend de las fases 7, 8 y 9, y por
eso se congela igual: leyendo el código.

No necesita base de datos: es introspección de las rutas registradas más
lectura de los archivos del frontend.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
REACT_ROOT = REPO_ROOT / "app" / "components" / "react"

#: Un enlace interno: lo que una persona puede **seguir**.
#:
#: Se reconoce por cómo se escribe —`href=`, o una asignación a
#: `window.location`—, y no por su forma. Esa distinción importa: las rutas de
#: la API empiezan igual (`/admin/...` puede ser una llamada, no una
#: pantalla) y meterlas aquí haría fallar el test por algo que nunca fue un
#: enlace. Lo que separa a las dos no es el texto: es quién las consume.
ENLACE = re.compile(
    r"""(?:href=\{?|window\.location(?:\.href)?\s*=\s*|location\.assign\()"""
    r"""\s*["'`](/(?:admin|login|profile)[^"'`\s]*)["'`]"""
)

#: `${...}` es un identificador que el servidor rellenará. Para comprobar la
#: FORMA de la ruta da igual cuál sea, así que se sustituye por un marcador.
INTERPOLACION = re.compile(r"\$\{[^}]*\}")

# ── Recolección ─────────────────────────────────────────────────────────────


def rutas_registradas() -> dict[str, str]:
    """`nombre de página -> patrón de ruta`, tal y como las sirve la aplicación.

    Se resuelve con `url_path_for`, que es el mismo mecanismo que usa la propia
    aplicación: si algún día el prefijo de un router cambiara, este test seguiría
    mirando la verdad y no una copia suya.
    """
    from app.main import frontend

    rutas: dict[str, str] = {}

    def recorrer(routes) -> None:
        for route in routes:
            if type(route).__name__ == "_IncludedRouter":
                recorrer(route.original_router.routes)
                continue
            nombre = getattr(route, "name", None)
            metodos = getattr(route, "methods", None) or set()
            if not nombre or "GET" not in metodos or type(route).__name__ == "Mount":
                continue
            parametros = {
                p: "1" for p in re.findall(r"\{(\w+)\}", getattr(route, "path", ""))
            }
            try:
                rutas[nombre] = str(frontend.url_path_for(nombre, **parametros))
            except Exception:  # noqa: BLE001 - una ruta sin nombre resoluble no es página
                continue

    recorrer(frontend.routes)
    return rutas


def _patron(ruta: str) -> str:
    """La forma de una ruta, con los identificadores normalizados.

    `/admin/records/7/profile` y `/admin/records/${id}/profile` son la misma
    ruta; lo que se compara es la forma.
    """
    ruta = INTERPOLACION.sub("1", ruta)
    ruta = ruta.split("?")[0].split("#")[0]
    return re.sub(r"/\d+(?=/|$)", "/1", ruta).rstrip("/") or "/"


#: Cualquier ruta de pantalla escrita en el codigo, la siga quien la siga.
#:
#: Se usa **solo** para preguntar «¿se puede llegar de aqui a alli?». Un enlace
#: puede pasar por una funcion auxiliar —una cola puede construir su destino en
#: `enlace(fila)` y asignarlo despues— y para la alcanzabilidad eso sigue
#: siendo un enlace. Para buscar rutas rotas no sirve, porque tambien atrapa
#: rutas de la API: por eso son dos colectores y no uno.
RUTA_DE_PANTALLA = re.compile(r"""["'`](/admin/[^"'`\s]*)["'`]""")


def enlaces_del_frontend() -> dict[str, set[str]]:
    """Cada enlace que una persona puede **seguir**, con el archivo que lo escribe."""
    encontrados: dict[str, set[str]] = {}

    for path in sorted(REACT_ROOT.rglob("*.ts*")):
        texto = path.read_text(encoding="utf-8")
        for bruto in ENLACE.findall(texto):
            patron = _patron(bruto)
            encontrados.setdefault(patron, set()).add(
                str(path.relative_to(REPO_ROOT))
            )
    return encontrados


def destinos_alcanzables() -> dict[str, set[str]]:
    """Cada ruta de pantalla nombrada, aunque llegue por una función auxiliar."""
    encontrados: dict[str, set[str]] = {}

    for path in sorted(REACT_ROOT.rglob("*.ts*")):
        texto = path.read_text(encoding="utf-8")
        for bruto in RUTA_DE_PANTALLA.findall(texto):
            patron = _patron(bruto)
            encontrados.setdefault(patron, set()).add(
                str(path.relative_to(REPO_ROOT))
            )
    return encontrados


# ── Comprobaciones ──────────────────────────────────────────────────────────


def test_every_internal_link_reaches_a_registered_page():
    """Ningún enlace interno lleva a una ruta que no existe.

    Un `href` es una cadena escrita a mano: no falla al compilar y no avisa a
    nadie. Lo único que hace es dar un 404 a quien lo pulse.
    """
    registradas = {_patron(p) for p in rutas_registradas().values()}
    enlaces = enlaces_del_frontend()

    rotos = {
        destino: sorted(archivos)
        for destino, archivos in enlaces.items()
        if destino not in registradas
    }

    assert not rotos, (
        "Estos enlaces del frontend no corresponden a ninguna ruta registrada:\n"
        + "\n".join(f"  {d}  <- {', '.join(a)}" for d, a in sorted(rotos.items()))
        + "\n\nRutas registradas:\n  "
        + "\n  ".join(sorted(registradas))
    )


NAVEGACION = REACT_ROOT / "app/providers/maincontent/config/navigation.ts"

#: Lo que es administración del sistema y no trabajo de negocio (D12-03).
PREFIJOS_DE_ADMINISTRACION = (
    "/admin/security/",
    "/admin/platform/",
    "/admin/companies/",
    "/admin/locations/",
)


def _menu(nombre: str) -> str:
    """El bloque de `navigation.ts` que declara un menú."""
    texto = NAVEGACION.read_text(encoding="utf-8")
    # `= [];` (menú vacío) o `= [\n ... \n];`
    encontrado = re.search(
        rf"export const {nombre}\b[^=]*=\s*\[(?:\];|.*?\n\];)", texto, re.S
    )
    assert encontrado, f"navigation.ts no declara `{nombre}`"
    return encontrado.group(0)


def _destinos(bloque: str) -> list[str]:
    return [d for d in re.findall(r"url:\s*'(/[^']*)'", bloque) if d != "#"]


@pytest.mark.parametrize("menu", ["businessNavigation", "administrationNavigation"])
def test_every_navigation_destination_is_a_registered_page(menu: str):
    """Ningún menú ofrece pantallas que no existan."""
    registradas = {_patron(p) for p in rutas_registradas().values()}
    rotos = [d for d in _destinos(_menu(menu)) if _patron(d) not in registradas]

    assert not rotos, f"`{menu}` apunta a rutas inexistentes: {rotos}"


@pytest.mark.parametrize("menu", ["businessNavigation", "administrationNavigation"])
def test_every_navigation_permission_exists_in_the_catalog(menu: str):
    """Un ítem con una capacidad inventada se esconde para todo el mundo.

    Y en silencio: el filtro oculta lo que no se puede abrir, así que una errata
    en el nombre del permiso no da error — hace desaparecer la pantalla.
    """
    from app.core.rbac.catalog import CAPABILITY_NAMES

    pedidas = set(re.findall(r"requiredPermission:\s*'([^']+)'", _menu(menu)))
    desconocidas = sorted(pedidas - CAPABILITY_NAMES)

    assert not desconocidas, (
        f"`{menu}` exige capacidades que no están en el catálogo: {desconocidas}"
    )


def test_the_sidebar_only_carries_business_work():
    """La administración no vuelve al menú lateral.

    Es la decisión D12-03: quien opera una orden de personal no tiene por qué
    atravesar Security y Platform para llegar a su trabajo.
    """
    intrusos = [
        d for d in _destinos(_menu("businessNavigation"))
        if d.startswith(PREFIJOS_DE_ADMINISTRACION)
    ]

    assert not intrusos, f"El menú lateral lleva administración: {intrusos}"


def test_every_administration_page_is_reachable_from_the_account_menu():
    """Sacar la administración del lateral no puede dejar pantallas huérfanas."""
    ofrecidas = {_patron(d) for d in _destinos(_menu("administrationNavigation"))}
    paginas = {
        nombre: ruta
        for nombre, ruta in rutas_registradas().items()
        if ruta.startswith(PREFIJOS_DE_ADMINISTRACION) and "{" not in ruta
    }
    huerfanas = sorted(
        nombre for nombre, ruta in paginas.items() if _patron(ruta) not in ofrecidas
    )

    assert paginas, "no se encontró ninguna página de administración registrada"
    assert not huerfanas, (
        f"Páginas de administración sin entrada en el menú de usuario: {huerfanas}"
    )


def test_each_menu_renders_from_the_shared_list():
    """Cada menú pinta su lista de `navigation.ts` y no declara rutas propias.

    Si el lateral o la barra superior volvieran a llevar sus destinos escritos a
    mano, habría otra vez dos listas, y la segunda acabaría diciendo algo
    distinto de la primera.
    """
    lateral = (REACT_ROOT / "app/providers/maincontent/ui/AppSidebar.tsx").read_text(
        encoding="utf-8"
    )
    barra = (REACT_ROOT / "widgets/Layout/AppTopbar.tsx").read_text(encoding="utf-8")

    assert "businessNavigation" in lateral
    assert "administrationNavigation" not in lateral
    assert not re.search(r"url:\s*'/", lateral), "AppSidebar declara rutas propias"

    assert "administrationNavigation" in barra
    assert "useVisibleNavigation" in barra, (
        "el menú de usuario tiene que filtrar con el mismo hook que el lateral"
    )


def test_no_internal_page_takes_its_context_from_browser_storage():
    """Un enlace directo autorizado tiene que poder reconstruir su página.

    El contexto de una pantalla interna —qué registro, qué compañía— lo imprime el servidor en el ancla de la página, o viaja en la
    query. Nunca en `localStorage` ni en `sessionStorage`.

    La diferencia se ve al pegar una URL: si el objeto de negocio viviera en el
    almacenamiento del navegador, la pantalla funcionaría al llegar desde otra y
    se rompería al abrirla directa o al recargar — y lo haría en silencio, con
    una pantalla vacía en vez de un error.
    """
    ofensores: list[str] = []
    for path in (REACT_ROOT / "pages").rglob("*.tsx"):
        texto = path.read_text(encoding="utf-8")
        if re.search(r"(localStorage|sessionStorage)", texto):
            ofensores.append(str(path.relative_to(REPO_ROOT)))

    assert not ofensores, (
        "Estas páginas internas toman contexto del almacenamiento del "
        "navegador, así que un enlace directo no las reconstruye: "
        + ", ".join(ofensores)
    )
