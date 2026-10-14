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

from app.routers_api.organization.models import CARGO_DE_ROL
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
