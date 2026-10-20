"""Endpoints de la captura periódica de ubicación (RTE-LOC-02).

* Configuración: `route.locationcapture.manage`, a demanda (ninguna plantilla de
  rol la concede).
* Ingesta: `route.worksession.execute`, como la evidencia de eventos: producir
  puntos de la propia jornada es parte de ejecutarla. La configuración efectiva
  la recibe quien ejecuta por `GET /api/location/policy`.

No hay ningún endpoint que lea muestras: la consulta de la línea de tiempo
(`location_point_timeline`) queda sin exponer hasta que exista una pantalla con
su propio permiso y alcance.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.locationcapture import service
from app.routers_api.locationcapture.schemas import (
    CaptureSettingRead,
    CaptureSettingUpdate,
    SamplesIn,
    SamplesResult,
)
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import require_permissions

router = APIRouter(tags=["Route Location Capture"])

GESTIONA = Depends(require_permissions(["route.locationcapture.manage"]))
EJECUTA = Depends(require_permissions(["route.worksession.execute"]))


@router.get("/location-capture/settings")
async def read_capture_settings(
    _authz: None = GESTIONA,
    company: TenantContext = Depends(get_company_required),
) -> CaptureSettingRead:
    return CaptureSettingRead.model_validate(await service.leer(company.id))


@router.put("/location-capture/settings")
async def update_capture_settings(
    payload: CaptureSettingUpdate,
    current_user: Users = Depends(get_current_user),
    _authz: None = GESTIONA,
    company: TenantContext = Depends(get_company_required),
) -> CaptureSettingRead:
    """Enciende, apaga o cambia el intervalo. 409 si otro guardó entre medias."""
    return CaptureSettingRead.model_validate(
        await service.guardar(company_id=company.id, actor_user_id=current_user.id, cambio=payload)
    )


@router.post("/location/samples")
async def ingest_location_samples(
    payload: SamplesIn,
    current_user: Users = Depends(get_current_user),
    _authz: None = EJECUTA,
    company: TenantContext = Depends(get_company_required),
) -> SamplesResult:
    """Un lote (≤ 50) de muestras de una jornada propia. Resultado por muestra."""
    resultados = await service.ingerir(
        company_id=company.id, user_id=current_user.id, lote=payload, recibido=datetime.now(timezone.utc),
    )
    return SamplesResult(results=resultados)
