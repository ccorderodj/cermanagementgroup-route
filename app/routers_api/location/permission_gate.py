"""La puerta de permiso de ubicación en el servidor (RTE10-A02, §11).

Qué puede y qué no puede garantizar el servidor
------------------------------------------------
El permiso de ubicación vive en el navegador y en el sistema operativo del
dispositivo. **El servidor no puede verlo.** Ninguna cabecera, ninguna firma y
ningún truco cambian eso: cualquier cosa que el cliente envíe sobre su propio
permiso es una afirmación suya, no una prueba.

Así que esto no finge comprobar lo que no se puede comprobar. Lo que hace es lo
más fuerte que la arquitectura permite de verdad:

* **exigir la afirmación.** Una transición que abre trabajo nuevo sin la
  cabecera, o con un valor distinto de `granted`, se rechaza. Un cliente que no
  pasó por la puerta del navegador no llega aquí por descuido;
* **dejarla auditada.** Cada intento bloqueado queda en `audit_event` con quién
  y qué estado declaró, que es lo que permite ver después si alguien operó sin
  permiso;
* **no debilitar la puerta del cliente.** §11 lo dice explícitamente: la
  limitación del servidor no es excusa para aflojar el bloqueo del navegador.

La frontera de confianza, dicha sin rodeos
-------------------------------------------
Un cliente modificado a mano puede enviar `granted` siendo falso. Eso es cierto
y es inevitable: es la misma frontera que ya tiene toda la evidencia de
ubicación —el navegador podría mentir sobre sus coordenadas— y que el producto
ya trata declarando la procedencia en vez de pretendiendo certeza.

Lo que esta puerta sí cierra es el caso real: el supervisor cuyo permiso está
revocado y cuyo cliente, legítimo, no puede abrir trabajo nuevo.

Qué NO se bloquea
-----------------
Cerrar lo que ya está abierto. Llegar, completar una parada, marcharse de ella
y terminar la jornada no pasan por aquí **a propósito** (§8): sin esa excepción,
revocar el permiso a mitad de un viaje dejaría ese viaje y esa jornada abiertos
para siempre. El producto prefiere un cierre veraz sin permiso a un registro
atrapado.

Y tampoco se bloquea la falta de señal. Esta puerta mira el permiso; que el GPS
no fije un punto es otra cosa, la resuelve el modelo de evidencia que ya existe
y §2.2 prohíbe expresamente convertirla en un bloqueo.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from app.core.audit.service import record_event
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users

#: La cabecera con la que el cliente declara su permiso al actuar.
CABECERA = "X-Location-Permission"

#: El único valor que abre trabajo nuevo. `prompt` no vale: es el estado de
#: quien todavía no ha decidido, y §2.1 lo pone del lado bloqueado.
CONCEDIDO = "granted"

#: Cabecera de RESPUESTA que marca el rechazo como "falta el permiso", para
#: que la cola durable lo distinga de un rechazo definitivo. Ver `raise` abajo.
RECHAZO = "X-Location-Permission-Required"

MENSAJE = (
    "Location access is required to start new work. Enable location for "
    "CER Route and try again."
)


def require_location_permission():
    """Exige que el cliente declare permiso concedido para abrir trabajo nuevo.

    Se monta sólo en las transiciones que **abren** un estado operativo. La
    lista de cuáles son no vive aquí: vive en el cliente
    (`shared/lib/location/operationalActions.ts`) y la cruza
    `tests/test_operational_action_matrix.py` contra lo que cada endpoint
    declara, para que las dos mitades no se separen.
    """

    async def dependencia(
        x_location_permission: str | None = Header(default=None, alias=CABECERA),
        current_user: Users = Depends(get_current_user),
        company: TenantContext = Depends(get_company_required),
    ) -> None:
        declarado = (x_location_permission or "").strip().lower()
        if declarado == CONCEDIDO:
            return

        # Se audita **antes** de rechazar: un intento bloqueado es justo el
        # hecho que §12 pide poder distinguir, y perderlo por lanzar primero
        # dejaría el incidente sin rastro.
        await record_event(
            company_id=company.id,
            entity_type="location_permission",
            entity_id=current_user.id,
            action="blocked",
            actor_user_id=current_user.id,
            summary="A new operational action was blocked: location permission is not granted",
            changes={"declared": declarado or None},
        )
        # La cabecera es lo que evita una perdida de datos real.
        #
        # La cola durable del cliente trata cualquier 4xx como definitivo y
        # BORRA la accion. Eso es correcto para un 409 o un 422, que diran lo
        # mismo dentro de una hora. No lo es para este rechazo: una accion
        # tomada sin cobertura ANTES de que existiera esta puerta no lleva la
        # asercion, y borrarla seria perder trabajo de campo real -- y, por el
        # orden de la cola, todo lo que dependia de ella--.
        #
        # Con la cabecera, la cola la conserva y la reintenta cuando vuelva el
        # permiso. No se identifica por el texto del mensaje: cambiar una frase
        # no puede convertir una espera en un borrado.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=MENSAJE,
            headers={RECHAZO: "true"},
        )

    return dependencia
