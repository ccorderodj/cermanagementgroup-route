"""
En qué producto se está administrando usuarios (A02-FC1, PD-02).

El problema que resuelve
------------------------
A02 acotó la asignación de roles mirando **quién llama**: si el actor tenía un rol
de producto de CER Route, sólo podía conceder roles de CER Route. Eso cerraba la
escalada, pero dejaba un hueco que CER detectó al revisarlo: un Superadmin o un
`owner` del núcleo entrando por `CER Route > Users` seguía recibiendo el catálogo
completo del tenant, y podía conceder `admin` desde una pantalla que dice CER
Route. La autoridad de quien mira no debería cambiar lo que una pantalla de
producto ofrece.

PD-02 lo corrige: **manda el contexto de producto, no el nivel de autoridad.**

Cómo se sabe el contexto, y por qué así
----------------------------------------
Por la **ruta**. El mismo router se monta dos veces:

    /api/users        → contexto núcleo, comportamiento intacto
    /api/route/users  → contexto CER Route, sólo los dos roles de producto

No es una cabecera que el cliente ponga —eso sería confiar en el cliente para
decidir una frontera— ni un parámetro que se pueda omitir: es el endpoint al que
se llama. La pantalla de CER Route llama a `/api/route/users` y **cualquiera** que
use ese contrato queda acotado, Superadmin incluido.

Y no duplica nada. Es literalmente el mismo `APIRouter` con los mismos handlers,
montado bajo dos prefijos; lo único que cambia es una dependencia que marca el
contexto. Escribir una segunda administración de usuarios habría creado un
segundo sitio donde arreglar el mismo fallo.

Sobre el `ContextVar`
---------------------
Cada petición corre en su propio contexto copiado (Starlette lo garantiza), así
que dos peticiones simultáneas no se pisan el valor. Se lee sólo dentro de la
petición que lo puso.
"""

from __future__ import annotations

from contextvars import ContextVar


#: Verdadero mientras se atiende una petición del contrato de CER Route.
#: Falso —el valor por defecto— para el contrato del núcleo, que no cambia.
_en_contexto_de_route: ContextVar[bool] = ContextVar(
    "usermanagement_contexto_route", default=False
)


async def marcar_contexto_de_route() -> None:
    """Dependencia que declara: esta petición viene de `CER Route > Users`."""
    _en_contexto_de_route.set(True)


def es_contexto_de_route() -> bool:
    """Si la petición actual llegó por el contrato de CER Route."""
    return _en_contexto_de_route.get()
