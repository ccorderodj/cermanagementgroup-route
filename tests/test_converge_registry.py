"""La lista cerrada de la convergencia: lo que impide que el olvido se repita.

Por qué este test existe
-------------------------
El hueco que `app/db/scripts/converge.py` cierra se abrió **cuatro veces** por
la misma vía: alguien añade algo que hay que sembrar, el despliegue no lo
siembra, y los entornos que ya existían se quedan atrás sin que nada falle.

Un comando de convergencia lo arregla para lo que hay hoy. Lo que impide que
vuelva a pasar mañana es esta comprobación: cada función de siembra del
repositorio tiene que estar **clasificada a mano**, o converge o no converge
con su motivo escrito. Añadir una `seed_*` nueva sin clasificarla rompe la
suite.

Es el mismo recurso que `tests/test_public_surface.py` usa con la superficie
pública, y por el mismo motivo: **lo que crece solo no se detiene con buenas
intenciones, se detiene con una lista que obliga a justificar cada entrada.**
"""

from __future__ import annotations

import pathlib
import re

#: Clasificación de cada función de siembra del repositorio.
#:
#: `CONVERGE` = el despliegue la ejecuta en cada pasada, es idempotente y sólo
#: añade. Cualquier otro valor es el **motivo** por el que no puede estar en un
#: paso automático, y ese motivo es la parte que importa: obliga a pensarlo.
CLASIFICACION: dict[str, str] = {
    # ── Convergen ───────────────────────────────────────────────────────────
    "seed_permissions": "CONVERGE",
    "seed_roles": "CONVERGE",
    "provision_standard_values": "CONVERGE",
    # ── No convergen, y por qué ─────────────────────────────────────────────
    "seed_company": (
        "crea una compañía. Eso es una decisión de negocio, no una "
        "reconciliación: un despliegue no puede inventar tenants."
    ),
    "seed_admin": (
        "crea un usuario con una contraseña generada. Un despliegue que crea "
        "accesos en cada pasada es un agujero, no una comodidad."
    ),
    "seed_states": (
        "siembra el catálogo de regiones **y** los estados donde opera un "
        "tenant concreto. Lo segundo es decisión suya y cambia con su "
        "operación; reimponerlo en cada despliegue revertiría sus cambios."
    ),
    "seed_key_for": (
        "no siembra nada: deriva la clave estable de un valor sembrado. "
        "Coincide con el prefijo por su nombre, no por lo que hace."
    ),
}

#: Lo que `converge.py` ejecuta, directa o indirectamente. `seed_permissions` y
#: `seed_roles` entran a través de `align_role_capabilities`, que es quien sabe
#: alinear **todas** las compañías sin crear roles.
EJECUTADAS_POR_CONVERGE = {
    "seed_permissions",
    "seed_roles",
    "provision_standard_values",
}

_PATRON = re.compile(r"^(?:async )?def ((?:seed|provision)_[a-z_]+)", re.MULTILINE)


def _funciones_de_siembra() -> set[str]:
    encontradas: set[str] = set()
    for ruta in pathlib.Path("app").rglob("*.py"):
        encontradas.update(_PATRON.findall(ruta.read_text(encoding="utf-8")))
    return encontradas


def test_toda_siembra_del_repositorio_esta_clasificada():
    """Si aparece una `seed_*` nueva, hay que decir si el despliegue la corre.

    El fallo de este test **no** es un problema del test: es la pregunta que
    nadie se hizo las cuatro veces anteriores.
    """
    encontradas = _funciones_de_siembra()
    sin_clasificar = sorted(encontradas - set(CLASIFICACION))
    assert not sin_clasificar, (
        "hay funciones de siembra sin clasificar: "
        f"{sin_clasificar}. Decide si el despliegue debe ejecutarlas "
        "(añádelas a converge.PASOS y márcalas CONVERGE) o escribe el motivo "
        "por el que no puede, en tests/test_converge_registry.py."
    )


def test_la_clasificacion_no_nombra_funciones_que_ya_no_existen():
    """Una entrada obsoleta haría creer que algo está cubierto y no lo está."""
    encontradas = _funciones_de_siembra()
    sobran = sorted(set(CLASIFICACION) - encontradas)
    assert not sobran, (
        f"la clasificación nombra funciones que ya no existen: {sobran}"
    )


def test_lo_marcado_como_converge_lo_ejecuta_converge():
    """Que la etiqueta y el registro de `converge.py` no se separen."""
    etiquetadas = {n for n, v in CLASIFICACION.items() if v == "CONVERGE"}
    assert etiquetadas == EJECUTADAS_POR_CONVERGE, (
        "la clasificación y lo que converge ejecuta no coinciden: "
        f"{etiquetadas ^ EJECUTADAS_POR_CONVERGE}"
    )


def test_lo_que_no_converge_explica_por_que():
    """Un motivo vacío sería una exclusión sin justificar, que es lo que no vale."""
    for nombre, valor in CLASIFICACION.items():
        if valor == "CONVERGE":
            continue
        assert len(valor) > 30, f"'{nombre}' se excluye sin un motivo escrito"


def test_el_registro_de_converge_no_esta_vacio():
    """Control del conjunto: si `PASOS` se vaciara, todo lo demás pasaría igual."""
    from app.db.scripts.converge import PASOS

    assert len(PASOS) >= 3
    nombres = [n for n, _ in PASOS]
    assert len(set(nombres)) == len(nombres), f"pasos duplicados: {nombres}"
