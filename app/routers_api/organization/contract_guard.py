"""
La jerarquía de CER Route sólo se cambia por el contrato de CER Route (V1.4, H-1).

El incidente que cierra
-----------------------
La administración general (`Access control → Users`, `/api/users`) compartía
los handlers con `CER Route → Users`, pero no pedía «Reports to» y no
sincronizaba el cargo. Desde ahí se pudo cambiar a `supervisor` el rol de un COO
con equipo: la persona quedó con rol de Supervisor y cargo de COO, y su rama
sin nadie con autoridad. Por CER Route la misma operación da 409.

La regla (DR-5)
---------------
Por el contrato general, **409** a todo lo que toque la jerarquía:

* cambiar el rol de quien tiene cargo vigente;
* dar un rol de la jerarquía (CEO … Sales, Supervisor incluido) a quien no lo
  tiene —en el alta, en la edición y en la readmisión—;
* enviar `superior_user_id`.

No se sincroniza ni se infiere el superior: esa pantalla no lo pide, y
adivinarlo es lo que V1.3 prohíbe. Lo demás del contrato general sigue igual:
editar nombre, correo o contraseña, mandar el mismo rol, roles del núcleo a
quien no está en el árbol, suspender, retirar.

Por qué aquí
------------
Es lógica de Route. El núcleo sólo la invoca: no sabe qué es un cargo.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.routers_api.organization.models import CARGO_DE_ROL, OrgPosition
from app.routers_api.organization.service import rol_en_compania, vigentes
from app.routers_api.usermanagement.product_context import es_contexto_de_route
from app.routers_api.usermanagement.role_policy import _nombre_del_rol

#: Código estable: la pantalla general lo lleva al campo del rol sin depender
#: de la redacción del mensaje.
CODIGO = "managed_in_cer_route"
MENSAJE = (
    "This person's role and reporting line are managed in CER Route → Users. "
    "Use CER Route → Users."
)


def _rechazo() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail={"code": CODIGO, "message": MENSAJE}
    )


async def exigir_contrato_de_route(
    *,
    company_id: int,
    user_id: int | None,
    role_id: int | None,
    superior_dado: bool,
) -> None:
    """409 si una petición del contrato general cambiaría la jerarquía.

    `user_id` nulo: alta (o readmisión, que entra como alta). Se llama **antes**
    de escribir nada, así que no hay cambio parcial que deshacer.
    """
    if es_contexto_de_route():
        return
    if superior_dado:
        raise _rechazo()
    if role_id is None:
        return
    nuevo = await _nombre_del_rol(role_id=role_id, company_id=company_id)
    if user_id is not None:
        actual = await rol_en_compania(
            company_id=company_id, user_id=user_id, incluir_suspendidos=True
        )
        if actual == nuevo:
            return
        if user_id in await vigentes(company_id):
            raise _rechazo()
    if nuevo in CARGO_DE_ROL:
        raise _rechazo()


# ── CEO y COO sólo cambian por «Replace manager» (V1.5) ─────────────────────

#: Los puestos de un solo titular en su nivel: cambiarlos con la lista de roles
#: generaba datos sin sentido (un CEO convertido en Supervisor con su árbol
#: colgando, un segundo CEO). Se relevan; no se editan.
ROLES_DE_RELEVO = frozenset({"CEO", "COO"})
CARGOS_DE_RELEVO = frozenset({OrgPosition.CEO, OrgPosition.COO})

CODIGO_RELEVO = "use_replace_manager"
MENSAJE_RELEVO = (
    "CEO and COO positions change only through “Replace manager” in "
    "CER Route → Users (available to the CER Route administrator)."
)


def _relevo() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": CODIGO_RELEVO, "message": MENSAJE_RELEVO},
    )


async def exigir_relevo_para_ceo_y_coo(
    *,
    company_id: int,
    user_id: int,
    role_id: int | None,
    superior_dado: bool,
    superior_user_id: int | None,
) -> None:
    """409 si una **edición** cambiaría un CEO o un COO, o haría a alguien CEO
    o COO. Enviar el mismo rol y el mismo superior no es un cambio.

    El alta no pasa por aquí: el primer CEO de una compañía y un COO nuevo
    (otro puesto, no un relevo) se siguen creando en el alta.
    """
    actual = await rol_en_compania(company_id=company_id, user_id=user_id, incluir_suspendidos=True)
    nuevo = await _nombre_del_rol(role_id=role_id, company_id=company_id) if role_id is not None else actual
    previa = (await vigentes(company_id)).get(user_id)
    cambia_rol = nuevo != actual
    cambia_superior = superior_dado and (
        previa is None or previa.superior_user_id != superior_user_id
    )
    if actual in ROLES_DE_RELEVO and (cambia_rol or cambia_superior):
        raise _relevo()
    # Regularizar no es ascender: si el cargo vigente **ya es** el del rol
    # (p. ej. rol Supervisor con cargo COO, de antes de V1.4), dar ese rol sólo
    # pone en orden lo que ya es, sin tocar el superior.
    regulariza = (
        previa is not None
        and previa.position == CARGO_DE_ROL.get(nuevo)
        and not cambia_superior
    )
    if cambia_rol and nuevo in ROLES_DE_RELEVO and not regulariza:
        raise _relevo()


def exigir_relevo_en_cargo(
    *, previo: str | None, nuevo: str | None, cambia_superior: bool = False
) -> None:
    """Lo mismo para la API de organización, que trabaja con cargos. `nuevo`
    nulo: se quita el cargo."""
    if previo in CARGOS_DE_RELEVO and (nuevo != previo or cambia_superior):
        raise _relevo()
    if nuevo in CARGOS_DE_RELEVO and nuevo != previo:
        raise _relevo()


# ── Un mando no se vacía a mano (V1.6) ──────────────────────────────────────

#: Puestos que tienen equipo. Su titular cambia con «Replace manager» y su
#: puesto se cierra con «Retire manager»; ninguno se vacía moviendo a la gente
#: una a una, que es como se suplantaba una sustitución sin heredar nada.
CARGOS_DE_MANDO = frozenset(
    {OrgPosition.CEO, OrgPosition.COO, OrgPosition.REGIONAL_MANAGER}
)

CODIGO_SIN_EQUIPO = "manager_left_without_team"
MENSAJE_SIN_EQUIPO = (
    "This would leave their manager without a team. To change who leads the "
    "team use “Replace manager”; to close the position use “Retire manager”."
)


async def exigir_que_el_mando_conserve_equipo(
    *,
    company_id: int,
    user_id: int,
    cambia_superior: bool,
    nuevo_superior: int | None,
    sale_del_arbol: bool,
) -> None:
    """409 si este movimiento deja a su jefe actual (CEO, COO o RM) sin
    ningún subordinado directo.

    Trasladar a **parte** del equipo sigue permitido, y también que alguien
    deje la compañía o se suspenda: eso no pasa por aquí.
    """
    actuales = await vigentes(company_id)
    previa = actuales.get(user_id)
    if previa is None or previa.superior_user_id is None:
        return
    jefe = previa.superior_user_id
    if not sale_del_arbol and (not cambia_superior or nuevo_superior == jefe):
        return
    fila_del_jefe = actuales.get(jefe)
    if fila_del_jefe is None or fila_del_jefe.position not in CARGOS_DE_MANDO:
        return
    if not any(a.superior_user_id == jefe and u != user_id for u, a in actuales.items()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": CODIGO_SIN_EQUIPO, "message": MENSAJE_SIN_EQUIPO},
        )
