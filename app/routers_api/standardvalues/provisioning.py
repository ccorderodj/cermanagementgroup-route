"""
Valores iniciales de las ocho listas, y cómo se siembran sin pisar al tenant.

Qué se siembra
--------------
Exactamente lo aprobado en el addendum RTE02-A01: ni sinónimos, ni valores de
más, ni los catálogos del prototipo que CER liberó a texto libre (destino de
visita, área de reclutamiento, referencia de empleado, oficina, área de
"Other"). Esta lista es la fuente para esa entrega; no se redescubre de ningún
otro sitio.

El problema difícil no es sembrar: es volver a sembrar
-------------------------------------------------------
Un aprovisionamiento que sólo evite duplicados no basta. Las cuatro cosas que
NO pueden pasar al re-ejecutarlo son:

1. duplicar lo que ya existe;
2. devolver a su nombre original un valor que el administrador **renombró**;
3. resucitar un valor que el administrador **borró**;
4. reactivar un valor que el administrador **desactivó**.

Comparar por etiqueta falla en los cuatro. En cuanto alguien renombra
"Escalated" a "Escalated to Manager", la siguiente siembra deja de reconocerlo
y crea un duplicado — y la lista se llena sola cada vez que se despliega.

Por eso la marca es `seed_key`: la identidad estable del valor sembrado, que
sobrevive al renombrado, a la desactivación y a la lápida. El aprovisionador
sólo hace una pregunta —"¿ya sembré esta clave en esta compañía?"— y si la
respuesta es sí, no toca nada. Una vez sembrado, el valor es del tenant.

`seed_key` es `NULL` para todo lo que cree el administrador: esos valores nunca
serán tocados por ninguna siembra, porque no los puso ninguna.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select

from app.routers_api.standardvalues.models import StandardValue, StandardValueList


@dataclass(frozen=True)
class ProvisioningResult:
    """Qué hizo el aprovisionamiento, para poder afirmarlo con evidencia."""

    created: int
    skipped: int

    @property
    def total(self) -> int:
        return self.created + self.skipped


#: Los valores exactos aprobados, en su orden. El orden de la tupla **es** el
#: `sort_order`: lo que CER numeró 1, 2, 3 aparece en ese orden en pantalla.
INITIAL_VALUES: dict[str, tuple[str, ...]] = {
    StandardValueList.CLIENT_VISIT_ACTIVITIES.value: (
        "Staffing Follow-up",
        "Service Review",
        "Attendance Follow-up",
        "Safety Follow-up",
    ),
    StandardValueList.RECRUITING_ACTIVITIES.value: (
        "Candidate Sourcing",
        "Hiring Event",
        "Referral Follow-up",
    ),
    StandardValueList.EMPLOYEE_VISIT_REASONS.value: (
        "Attendance Issue",
        "Document Follow-up",
        "Transportation Issue",
        "Employee Support",
    ),
    StandardValueList.DELIVERY_TYPES.value: (
        "Payroll Check",
        "Document Delivery",
        "Equipment Delivery",
    ),
    StandardValueList.OFFICE_PURPOSES.value: (
        "Paperwork",
        "Meeting",
        "Pickup / Drop-off",
        "Administrative Follow-up",
    ),
    StandardValueList.OTHER_ACTIVITIES.value: (
        "Housing Visit",
        "Transportation Support",
        "Supply Pickup",
    ),
    StandardValueList.OUTCOMES.value: (
        "Completed",
        "Follow-up Required",
        "Escalated",
        "No Contact",
    ),
    StandardValueList.RECEIVED_BY.value: (
        "Employee",
        "Authorized Person",
        "Office Staff",
    ),
}


def seed_key_for(list_code: str, label: str) -> str:
    """Identidad estable de un valor sembrado: `lista:etiqueta_normalizada`.

    Se deriva de la etiqueta **aprobada**, no de la que tenga la fila en cada
    momento: es lo que permite que renombrarla no rompa el reconocimiento.
    """
    ranura = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return f"{list_code}:{ranura}"


async def provision_standard_values(session, *, company_id: int) -> ProvisioningResult:
    """Siembra lo que falte en esta compañía, y **nada más**.

    Acotado por `company_id` en las dos direcciones: sólo lee y sólo escribe
    filas de esa compañía, así que sembrar un tenant no puede tocar a otro.

    No hace `commit`: lo decide quien llama, que normalmente está dentro de una
    transacción mayor —crear la compañía y sembrarla son un solo hecho—.
    """
    filas = await session.execute(
        select(StandardValue.seed_key).where(
            StandardValue.company_id == company_id,
            StandardValue.seed_key.is_not(None),
        )
    )
    #: Deliberadamente **sin** filtrar `deleted_at` ni `is_active`: la pregunta
    #: es "¿ya sembré esto?", no "¿sigue vivo?". Mirar sólo lo vivo resucitaría
    #: en cada despliegue todo lo que el administrador hubiera quitado.
    ya_sembradas = {clave for (clave,) in filas.all()}

    creados = 0
    omitidos = 0

    for list_code, etiquetas in INITIAL_VALUES.items():
        for posicion, etiqueta in enumerate(etiquetas, start=1):
            clave = seed_key_for(list_code, etiqueta)
            if clave in ya_sembradas:
                omitidos += 1
                continue

            session.add(
                StandardValue(
                    company_id=company_id,
                    list_code=list_code,
                    label=etiqueta,
                    sort_order=posicion,
                    seed_key=clave,
                )
            )
            creados += 1

    await session.flush()
    return ProvisioningResult(created=creados, skipped=omitidos)
