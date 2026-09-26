"""
Los valores iniciales de los catálogos, contra el documento que los aprobó.

Por qué esta red no es redundante
----------------------------------
`tests/integration/test_admin_lifecycle.py` ya comprueba que la base acaba con
lo que dice `INITIAL_VALUES`. Eso protege el aprovisionamiento, pero **no**
protege los valores: si alguien edita `INITIAL_VALUES` —cambia una etiqueta por
un sinónimo, reordena, añade uno de más— ese test sigue pasando, porque el
código se estaría comparando consigo mismo.

La fuente de verdad es el documento de CER, y está en el repositorio. Así que se
parsea y se compara. La instrucción es explícita sobre las tres formas de
divergir, y las tres se comprueban:

    Do not replace them with synonyms.
    Do not add extra values.
    Do not rediscover them from the prototype; this file is the approved source.

El orden también importa: la instrucción numera los valores, y ese número **es**
el `sort_order` con el que aparecen en el móvil del supervisor.

Y ahora importa más que cuando se escribieron. RTE04 hizo obligatorios tres de
estos catálogos antes de `Start Trip`, así que una lista sin valores ya no es una
pantalla incompleta: es un tipo de viaje que no se puede arrancar.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.routers_api.standardvalues.models import StandardValueList
from app.routers_api.standardvalues.provisioning import INITIAL_VALUES
from app.routers_api.trips.models import PRETRIP_STANDARD_LIST


#: El documento que aprobó estos valores, y que la propia instrucción declara
#: fuente única: "this file is the approved source for this Addendum".
FUENTE_APROBADA = (
    Path(__file__).resolve().parents[1]
    / "_cer_delivery"
    / "CER_ROUTE_RTE02_ADDENDUM_A01_DEVELOPMENT_INSTRUCTIONS_004.md"
)

#: Los títulos del documento y el código de lista al que corresponden. Se escribe
#: a mano a propósito: derivarlo del título con una regla automática convertiría
#: un cambio de nombre en una coincidencia falsa.
TITULO_A_CODIGO = {
    "Client Visit Activities": StandardValueList.CLIENT_VISIT_ACTIVITIES.value,
    "Recruiting Activities": StandardValueList.RECRUITING_ACTIVITIES.value,
    "Employee Visit Reasons": StandardValueList.EMPLOYEE_VISIT_REASONS.value,
    "Delivery Types": StandardValueList.DELIVERY_TYPES.value,
    "Office Purposes": StandardValueList.OFFICE_PURPOSES.value,
    "Other Activities": StandardValueList.OTHER_ACTIVITIES.value,
    "Outcomes": StandardValueList.OUTCOMES.value,
    "Received By": StandardValueList.RECEIVED_BY.value,
}


def _valores_aprobados() -> dict[str, list[str]]:
    """Lee las listas del documento: `### Título` y luego `N. \\`Etiqueta\\``."""
    texto = FUENTE_APROBADA.read_text(encoding="utf-8")
    seccion = texto.split("## Initial Standardized Values")[1]
    seccion = seccion.split("## Fields That Must Remain Free Text")[0]

    encontrado: dict[str, list[str]] = {}
    actual: str | None = None
    for linea in seccion.splitlines():
        limpia = linea.strip()
        if limpia.startswith("### "):
            actual = limpia[4:].strip()
            encontrado[actual] = []
        elif actual is not None:
            numerado = re.match(r"^\d+\.\s+`(.+)`$", limpia)
            if numerado:
                encontrado[actual].append(numerado.group(1))
    return encontrado


APROBADOS = _valores_aprobados()


def test_the_approved_source_document_is_still_readable():
    """Si el documento se mueve o cambia de formato, esta red avisa.

    Falla ruidosamente en vez de quedarse sin nada que comparar y pasar en
    verde, que sería lo peor que podría hacer.
    """
    assert FUENTE_APROBADA.is_file(), f"no está el documento: {FUENTE_APROBADA}"
    assert len(APROBADOS) == 8, f"se leyeron {len(APROBADOS)} listas, no 8"
    assert all(APROBADOS.values()), "alguna lista se leyó vacía"


def test_every_approved_list_exists_in_the_product_enum():
    """Las ocho listas son producto: el enum y el documento dicen lo mismo."""
    del_documento = set(TITULO_A_CODIGO[t] for t in APROBADOS)
    del_enum = {codigo.value for codigo in StandardValueList}
    assert del_documento == del_enum


@pytest.mark.parametrize("titulo", sorted(APROBADOS))
def test_each_list_seeds_exactly_the_approved_values_in_order(titulo):
    """Ni sinónimos, ni valores de más, ni otro orden.

    El orden no es estético: el número del documento es el `sort_order` con el
    que el supervisor los ve en el teléfono.
    """
    codigo = TITULO_A_CODIGO[titulo]
    assert list(INITIAL_VALUES[codigo]) == APROBADOS[titulo], (
        f"'{titulo}' divergió del documento aprobado"
    )


def test_the_provisioning_table_adds_nothing_of_its_own():
    """Ninguna lista sembrada que el documento no apruebe."""
    sobrantes = set(INITIAL_VALUES) - set(TITULO_A_CODIGO.values())
    assert sobrantes == set(), f"listas sin aprobar: {sorted(sobrantes)}"


def test_the_lists_required_before_departure_are_never_seeded_empty():
    """Los tres catálogos que RTE04 hizo obligatorios nacen con valores.

    Desde RTE04, un viaje de Employee Visit, Check Delivery u Office no arranca
    sin su valor de lista. Si el aprovisionamiento dejara una de esas listas
    vacía, el tipo de viaje sería **inarrancable** en una compañía nueva, y el
    supervisor vería que se le pide elegir algo que no existe.

    Un administrador **sí** puede vaciarlas después; eso es comportamiento de
    configuración ya certificado y no se toca aquí. Lo que esta red garantiza es
    que no ocurra de fábrica.
    """
    for purpose, list_code in PRETRIP_STANDARD_LIST.items():
        sembrados = INITIAL_VALUES.get(list_code, ())
        assert sembrados, (
            f"'{list_code}' es obligatoria antes de salir para '{purpose}' "
            "y se sembraría vacía"
        )
