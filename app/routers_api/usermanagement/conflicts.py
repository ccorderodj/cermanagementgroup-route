"""
Los conflictos de creación de usuario, con nombre propio.

Por qué existe este módulo
--------------------------
Hasta A03 el servidor devolvía frases en inglés y la pantalla las mostraba en un
aviso genérico. Eso tenía dos consecuencias: el administrador veía
`Submission failed` sin saber qué hacer, y cualquier intento de reaccionar en el
cliente habría tenido que **leer el texto** — un contrato que se rompe el día
que alguien mejore una redacción o traduzca la interfaz.

Así que cada situación conocida tiene un código estable. La pantalla decide con
el código; el texto es para la persona.

Qué **no** se dice
------------------
Que un nombre de usuario existe en otra compañía. Ese hecho no pertenece a este
tenant, y contarlo convertiría el formulario en un enumerador de clientes: se
responde `USERNAME_UNAVAILABLE`, que es cierto y no revela nada (D-A03-05).

Sobre la pertenencia **propia** sí se habla: que alguien estuvo en esta compañía
es información de esta compañía, y es justo la que hace posible readmitirlo.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from fastapi import HTTPException, status
from sqlalchemy import select

from app.core.db.session import db_session
from app.routers_api.companies.models import UserCompany
from app.routers_api.users.models import Users


class UserConflict(StrEnum):
    """Lo que puede impedir crear un usuario, y qué salida tiene cada caso."""

    #: Ya trabaja aquí y su acceso está vivo. No hay nada que hacer.
    SAME_TENANT_ACTIVE = "same_tenant_active"
    #: Trabaja aquí pero su acceso está suspendido. Se reactiva, no se recrea.
    SAME_TENANT_INACTIVE = "same_tenant_inactive"
    #: Estuvo aquí y se le retiró el acceso. Se puede readmitir, con confirmación.
    SAME_TENANT_REMOVED = "same_tenant_removed"
    #: El nombre está tomado en la plataforma y esta compañía no tiene historia
    #: con él. No se dice más que eso.
    USERNAME_UNAVAILABLE = "username_unavailable"
    #: El rol pedido no es asignable desde CER Route.
    ROLE_NOT_ALLOWED = "role_not_allowed"


#: El texto para la persona. El código es para la pantalla; esto es para quien
#: la mira, y por eso dice qué ocurre y no qué tabla lo dice.
MENSAJES: dict[UserConflict, str] = {
    UserConflict.SAME_TENANT_ACTIVE: (
        "A user with this username already exists in this company."
    ),
    UserConflict.SAME_TENANT_INACTIVE: (
        "This user already exists in this company and their access is "
        "inactive. Reactivate them instead of creating a new user."
    ),
    UserConflict.SAME_TENANT_REMOVED: (
        "This user previously belonged to this company."
    ),
    UserConflict.USERNAME_UNAVAILABLE: "This username is unavailable.",
    UserConflict.ROLE_NOT_ALLOWED: (
        "That role cannot be assigned from CER Route."
    ),
}


def conflicto(
    codigo: UserConflict,
    *,
    user_id: int | None = None,
    nombre: str | None = None,
) -> HTTPException:
    """Un 409 con código, mensaje y lo justo para poder actuar.

    `user_id` y `nombre` viajan **sólo** en los casos del propio tenant: son
    datos que esta compañía ya puede ver en su lista de usuarios, y sin el
    identificador la pantalla no podría ofrecer readmitir a nadie. En
    `USERNAME_UNAVAILABLE` no se envían, porque ahí no hay nada que esta
    compañía tenga derecho a saber.
    """
    detalle: dict[str, object] = {
        "code": codigo.value,
        "message": MENSAJES[codigo],
    }
    if user_id is not None:
        detalle["user_id"] = user_id
    if nombre is not None:
        detalle["display_name"] = nombre

    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)


@dataclass(frozen=True)
class EstadoDelNombre:
    """Qué sabe esta compañía sobre ese nombre de usuario."""

    conflicto: UserConflict | None
    user_id: int | None = None
    display_name: str | None = None
    #: La pertenencia histórica, cuando la hay. Sólo del tenant que pregunta.
    membership_id: int | None = None


async def clasificar_nombre(*, username: str, company_id: int) -> EstadoDelNombre:
    """Clasifica un nombre de usuario **antes** de intentar escribir.

    Antes esto se averiguaba dejando fallar la restricción de la base y
    traduciendo el nombre del índice violado. Funcionaba para decir "está
    tomado" y no podía decir nada más: un `IntegrityError` no distingue entre
    alguien que trabaja aquí, alguien suspendido y alguien a quien se retiró el
    acceso hace un año. Y esas tres cosas tienen tres salidas distintas.

    La consulta de la pertenencia **no** filtra la lápida a propósito: es
    exactamente la fila que hace posible readmitir, y la consulta normal la
    esconde.
    """
    async with db_session() as session:
        usuario = await session.scalar(
            select(Users).where(Users.username == username.strip())
        )
        if usuario is None:
            return EstadoDelNombre(conflicto=None)

        pertenencia = await session.scalar(
            select(UserCompany).where(
                UserCompany.user_id == usuario.id,
                UserCompany.company_id == company_id,
            )
        )

    nombre = f"{usuario.first_name} {usuario.last_name}".strip() or usuario.username

    if pertenencia is None:
        # La identidad existe en la plataforma, pero esta compañía no tiene
        # historia con ella. No se dice de quién es (D-A03-05, FR-10).
        return EstadoDelNombre(conflicto=UserConflict.USERNAME_UNAVAILABLE)

    if pertenencia.deleted_at is not None:
        return EstadoDelNombre(
            conflicto=UserConflict.SAME_TENANT_REMOVED,
            user_id=usuario.id,
            display_name=nombre,
            membership_id=pertenencia.id,
        )

    if pertenencia.is_active:
        return EstadoDelNombre(
            conflicto=UserConflict.SAME_TENANT_ACTIVE,
            user_id=usuario.id,
            display_name=nombre,
            membership_id=pertenencia.id,
        )

    return EstadoDelNombre(
        conflicto=UserConflict.SAME_TENANT_INACTIVE,
        user_id=usuario.id,
        display_name=nombre,
        membership_id=pertenencia.id,
    )


async def clasificar_nombre_por_id(
    *, user_id: int, company_id: int
) -> EstadoDelNombre:
    """Lo mismo, pero partiendo del identificador.

    Lo usa la readmisión: la pantalla ya sabe a quién readmite porque el
    conflicto se lo dijo, y volver a buscar por nombre de usuario abriría la
    puerta a readmitir a otra persona si el nombre cambió entretanto.
    """
    async with db_session() as session:
        usuario = await session.scalar(select(Users).where(Users.id == user_id))
        if usuario is None:
            return EstadoDelNombre(conflicto=UserConflict.USERNAME_UNAVAILABLE)

        pertenencia = await session.scalar(
            select(UserCompany).where(
                UserCompany.user_id == user_id,
                UserCompany.company_id == company_id,
            )
        )

    nombre = f"{usuario.first_name} {usuario.last_name}".strip() or usuario.username

    if pertenencia is None:
        return EstadoDelNombre(conflicto=UserConflict.USERNAME_UNAVAILABLE)
    if pertenencia.deleted_at is not None:
        return EstadoDelNombre(
            conflicto=UserConflict.SAME_TENANT_REMOVED,
            user_id=user_id,
            display_name=nombre,
            membership_id=pertenencia.id,
        )
    if pertenencia.is_active:
        return EstadoDelNombre(
            conflicto=UserConflict.SAME_TENANT_ACTIVE,
            user_id=user_id,
            display_name=nombre,
            membership_id=pertenencia.id,
        )
    return EstadoDelNombre(
        conflicto=UserConflict.SAME_TENANT_INACTIVE,
        user_id=user_id,
        display_name=nombre,
        membership_id=pertenencia.id,
    )
