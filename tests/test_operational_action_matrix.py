"""La matriz de acciones operativas, cruzada contra el código real (§14).

Qué defiende
------------
La puerta de ubicación vive en dos mitades que pueden separarse sin que nada
falle:

* el **cliente** clasifica cada acción en `operationalActions.ts` — abre trabajo
  nuevo, o cierra lo que ya estaba;
* el **servidor** monta `require_location_permission` en los endpoints que
  abren.

Si alguien añade una transición nueva y sólo toca una mitad, el checkpoint queda
con un agujero y todo sigue verde. Este archivo lo impide: lee las tres fuentes
—la clasificación, las llamadas a `enqueueAction` y los decoradores de los
routers— y exige que digan lo mismo.

§14 lo pide con una frase que resume el riesgo: *«no se fíe sólo de los nombres
de los botones»*. Por eso aquí no se deduce nada del nombre; se compara código
contra código.
"""

from __future__ import annotations

import pathlib
import re

RAIZ = pathlib.Path("app/components/react")
CLASIFICACION = RAIZ / "shared/lib/location/operationalActions.ts"

#: Los routers donde viven las transiciones operativas.
ROUTERS = (
    pathlib.Path("app/routers_api/trips/router.py"),
    pathlib.Path("app/routers_api/activities/router.py"),
    pathlib.Path("app/routers_api/worksessions/router.py"),
)

GUARDA = "require_location_permission()"


def _lista(nombre: str) -> set[str]:
    """Lee una de las listas de la clasificación del cliente."""
    texto = CLASIFICACION.read_text(encoding="utf-8")
    bloque = re.search(
        rf"export const {nombre}: readonly string\[\] = \[(.*?)\];", texto, re.S
    )
    assert bloque, f"no se encontró la lista {nombre}"
    return set(re.findall(r"'([^']+)'", bloque.group(1)))


def _encoladas() -> dict[str, str]:
    """Cada `kind` que el código encola, con el endpoint al que va.

    `activity.${action}` se expande a sus dos valores terminales: el tipo
    `TerminalAction` sólo admite `complete` y `leave`, así que la expansión es
    exhaustiva y no una suposición.
    """
    encontradas: dict[str, str] = {}
    for ruta in RAIZ.rglob("*.ts"):
        texto = ruta.read_text(encoding="utf-8")
        for kind, endpoint in re.findall(
            r"enqueueAction\(\s*[`']([^`']+)[`']\s*,\s*[`']([^`']+)[`']", texto
        ):
            if "${action}" in kind:
                for terminal in ("complete", "leave"):
                    encontradas[kind.replace("${action}", terminal)] = (
                        endpoint.replace("${action}", terminal)
                    )
            else:
                encontradas[kind] = endpoint
    return encontradas


def _endpoints_con_guarda() -> set[str]:
    """Las rutas cuyo handler declara `require_location_permission`."""
    protegidas: set[str] = set()
    for ruta in ROUTERS:
        lineas = ruta.read_text(encoding="utf-8").split("\n")
        prefijo = ""
        base = re.search(r'prefix="([^"]*)"', ruta.read_text(encoding="utf-8"))
        if base:
            prefijo = base.group(1)
        for i, linea in enumerate(lineas):
            decorador = re.match(r'@router\.post\("([^"]*)"\)', linea.strip())
            if not decorador:
                continue
            # El cuerpo de la firma, hasta el `)` que la cierra.
            firma = "\n".join(lineas[i : i + 24])
            if GUARDA in firma.split(") ->")[0]:
                protegidas.add(prefijo + decorador.group(1))
    return protegidas


def _normalizar(endpoint: str) -> str:
    """`/trips/${tripId}/start` -> `/trips/{}/start`, para poder comparar."""
    sin_api = endpoint.removeprefix("/api")
    return re.sub(r"\$\{[^}]+\}|\{[^}]+\}", "{}", sin_api)


# ── La clasificación cubre todo lo que se encola ────────────────────────────


def test_toda_accion_encolada_esta_clasificada():
    """Una transición nueva sin clasificar rompe la suite.

    Es la comprobación que impide que la próxima acción operativa nazca fuera
    de la puerta sin que nadie lo note.
    """
    conocidas = _lista("ABRE_TRABAJO_NUEVO") | _lista("CIERRA_TRABAJO_ABIERTO")
    encoladas = set(_encoladas())
    sin_clasificar = sorted(encoladas - conocidas)
    assert not sin_clasificar, (
        f"acciones operativas sin clasificar: {sin_clasificar}. Decide en "
        "shared/lib/location/operationalActions.ts si abren trabajo nuevo "
        "(exigen permiso) o cierran lo ya abierto (no lo exigen)."
    )


def test_la_clasificacion_no_nombra_acciones_que_no_existen():
    """Una entrada obsoleta haría creer que algo está cubierto y no lo está."""
    conocidas = _lista("ABRE_TRABAJO_NUEVO") | _lista("CIERRA_TRABAJO_ABIERTO")
    sobran = sorted(conocidas - set(_encoladas()))
    assert not sobran, f"la clasificación nombra acciones que ya no se encolan: {sobran}"


def test_ninguna_accion_abre_y_cierra_a_la_vez():
    """Las dos listas son excluyentes: una acción no puede ser las dos cosas."""
    ambas = _lista("ABRE_TRABAJO_NUEVO") & _lista("CIERRA_TRABAJO_ABIERTO")
    assert not ambas, f"clasificadas en las dos listas: {sorted(ambas)}"


# ── El servidor y el cliente dicen lo mismo ─────────────────────────────────


def test_lo_que_abre_trabajo_esta_protegido_en_el_servidor():
    """La mitad del servidor, cruzada con la del cliente.

    Bloquear sólo en el navegador no es bloquear: una petición a mano se lo
    salta. Este test exige que cada transición clasificada como «abre» lleve
    la guarda en su endpoint.
    """
    protegidos = {_normalizar(e) for e in _endpoints_con_guarda()}
    encoladas = _encoladas()
    desprotegidas = sorted(
        kind
        for kind in _lista("ABRE_TRABAJO_NUEVO")
        if _normalizar(encoladas[kind]) not in protegidos
    )
    assert not desprotegidas, (
        f"abren trabajo nuevo y su endpoint no exige permiso: {desprotegidas}. "
        "Añade `Depends(require_location_permission())` a su handler."
    )


def test_lo_que_cierra_NO_esta_protegido_en_el_servidor():
    """La otra mitad, y es la que un refuerzo con prisa rompe.

    Si cerrar exigiera permiso, revocarlo a mitad de un viaje dejaría ese viaje
    y esa jornada abiertos para siempre. §8 existe precisamente para que eso no
    pase, y este test es lo que impide «proteger de más».
    """
    protegidos = {_normalizar(e) for e in _endpoints_con_guarda()}
    encoladas = _encoladas()
    atrapadas = sorted(
        kind
        for kind in _lista("CIERRA_TRABAJO_ABIERTO")
        if _normalizar(encoladas[kind]) in protegidos
    )
    assert not atrapadas, (
        f"cierran lo ya abierto y su endpoint exige permiso: {atrapadas}. "
        "Eso atrapa registros abiertos cuando el permiso se revoca a mitad."
    )


def test_la_matriz_no_esta_vacia():
    """Control del conjunto: si los extractores dejaran de encontrar nada,
    todos los tests de arriba pasarían sin comprobar nada."""
    assert len(_encoladas()) >= 8, _encoladas()
    assert len(_lista("ABRE_TRABAJO_NUEVO")) >= 4
    assert len(_lista("CIERRA_TRABAJO_ABIERTO")) >= 5
    assert len(_endpoints_con_guarda()) >= 4, _endpoints_con_guarda()
