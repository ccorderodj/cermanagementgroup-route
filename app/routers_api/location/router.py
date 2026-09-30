"""Endpoints de evidencia de ubicación (RTE06-CP2, §31).

Dos endpoints y nada más. §31 delega los nombres y enumera capacidades:
sincronizar evidencia atada a una acción, y finalizar Missing al agotarse la
ventana. Las demás capacidades que lista —consultar kilometraje, reintentar,
barrer— son del módulo `mileage`, porque son otro dominio.

Autorización
------------
`route.worksession.execute`, la misma capacidad que ya ejecuta la jornada. §34
dice que no se añada capacidad sin un hueco demostrado, y no lo hay: producir
evidencia de la propia ruta es parte de ejecutarla. Que el punto sea **del
propio** supervisor no lo decide el permiso sino el servicio, resolviendo el
sujeto contra su jornada.

`Idempotency-Key` no se usa aquí
--------------------------------
Y es deliberado. La idempotencia de esta escritura ya la da el índice único de
la correlación `(company_id, event_kind, subject_kind, subject_id)`, que es más
fuerte: protege incluso si el cliente pierde la clave o la regenera, cosa que
pasa al reinstalar la aplicación. Añadir la cabecera daría dos mecanismos para
lo mismo y un sitio más donde equivocarse.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from app.routers_api.users.permissions import require_permissions
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.location.schemas import (
    LocationEvidenceIn,
    LocationEvidenceRead,
    MissingLocationIn,
    MissingLocationRead,
)
from app.routers_api.location.service import LocationEvidenceService
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users

router = APIRouter(prefix="/location", tags=["Route Location"])

EJECUTA = Depends(require_permissions(["route.worksession.execute"]))


@router.post("/evidence", status_code=status.HTTP_201_CREATED)
async def sync_location_evidence(
    payload: LocationEvidenceIn,
    current_user: Users = Depends(get_current_user),
    _authz: None = EJECUTA,
    company: TenantContext = Depends(get_company_required),
) -> LocationEvidenceRead:
    """Registra el punto capturado para un evento del ciclo de vida.

    Devuelve 201 también cuando el punto ya estaba: el reenvío de la cola
    offline hizo lo correcto, y `replayed` lo dice sin que el cliente tenga que
    tratar un conflicto que no lo es.
    """
    fila, reenvio = await LocationEvidenceService.record(
        company_id=company.id,
        user_id=current_user.id,
        payload=payload,
        # La hora de recepción la pone el servidor, siempre. §31: la ocurrencia
        # y la recepción son dos hechos distintos y ninguno llega del cuerpo.
        received_at=datetime.now(timezone.utc),
    )
    respuesta = LocationEvidenceRead.model_validate(fila)
    return respuesta.model_copy(update={"replayed": reenvio})


@router.post("/missing", status_code=status.HTTP_201_CREATED)
async def finalize_missing_location(
    payload: MissingLocationIn,
    current_user: Users = Depends(get_current_user),
    _authz: None = EJECUTA,
    company: TenantContext = Depends(get_company_required),
) -> MissingLocationRead:
    """Da por perdida la ubicación de un evento tras agotar la ventana."""
    fila, reenvio = await LocationEvidenceService.finalize_missing(
        company_id=company.id, user_id=current_user.id, payload=payload
    )
    respuesta = MissingLocationRead.model_validate(fila)
    return respuesta.model_copy(update={"replayed": reenvio})
