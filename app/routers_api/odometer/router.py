"""
API de la evidencia de odómetro.

Dos autoridades distintas, y no se mezclan
-------------------------------------------
* El **supervisor** aporta evidencia de su propia jornada:
  `route.worksession.execute`, el mismo permiso con el que ejecuta su trabajo
  de campo.
* El **administrador** decide sobre una excepción: `route.records.adjust`. No
  se le concede a un supervisor por el hecho de ser dueño de la jornada —
  aprobar tu propia excepción vaciaría de sentido el control.

La foto nunca tiene URL pública. Se sirve por un endpoint que comprueba tenant
y propiedad en cada lectura, porque puede mostrar salpicadero, matrícula o
kilometraje real del vehículo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.odometer.dao import (
    OdometerEvidenceDAO,
    OdometerExceptionRequestsDAO,
)
from app.routers_api.odometer.models import OdometerEvidenceType
from app.routers_api.odometer.schemas import (
    OdometerEvidenceRead,
    OdometerExceptionCreate,
    OdometerExceptionQueueRead,
    OdometerExceptionRead,
    OdometerPhotoResult,
    OdometerReadingConfirm,
    OdometerSessionState,
)
from app.routers_api.odometer.service import OdometerService
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import has_permissions, require_permissions
from app.routers_api.worksessions.dao import WorkSessionsDAO


router = APIRouter(prefix="/odometer", tags=["Route · Odometer"])

#: 12 MB. Una foto de móvil cabe de sobra; más que eso es un envío que no
#: describe un cuentakilómetros.
_MAX_BYTES = 12 * 1024 * 1024


async def _jornada_propia(*, company_id: int, user_id: int, work_session_id: int):
    """La jornada tiene que ser de quien llama. 404 si no, sin distinguir."""
    jornada = await WorkSessionsDAO.get_for_company_and_owner(
        session_id=work_session_id, company_id=company_id, user_id=user_id
    )
    if jornada is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Work session not found"
        )
    return jornada


@router.get("/sessions/{work_session_id}")
async def get_session_odometer(
    work_session_id: int,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> OdometerSessionState:
    """Los dos extremos de una jornada propia, y su distancia si ya existe."""
    await _jornada_propia(
        company_id=company.id, user_id=current_user.id, work_session_id=work_session_id
    )

    inicio, fin, distancia = await OdometerService.session_state(
        company_id=company.id, work_session_id=work_session_id
    )

    return OdometerSessionState(
        start=OdometerEvidenceRead.model_validate(inicio),
        end=OdometerEvidenceRead.model_validate(fin) if fin else None,
        odometer_distance=distancia,
    )


@router.post("/sessions/{work_session_id}/{evidence_type}/photo")
async def upload_photo(
    work_session_id: int,
    evidence_type: OdometerEvidenceType,
    photo: UploadFile = File(...),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> OdometerPhotoResult:
    """Sube la foto del cuentakilómetros e intenta una sugerencia.

    La clave de almacenamiento la genera el servidor: derivarla del nombre que
    envía quien sube el archivo es justo lo que las reglas del repositorio
    prohíben.

    `ocr_suggestion` puede venir vacía, y es normal: el OCR es asistivo. Sin
    sugerencia el supervisor teclea lo que ve en la foto, y eso sigue siendo
    evidencia fotográfica sin aprobación de nadie.
    """
    await _jornada_propia(
        company_id=company.id, user_id=current_user.id, work_session_id=work_session_id
    )

    contenido = await photo.read()
    if not contenido:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The photo is empty.",
        )
    if len(contenido) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That photo is too large. Take a new one.",
        )

    evidencia, sugerencia = await OdometerService.attach_photo(
        company_id=company.id,
        work_session_id=work_session_id,
        evidence_type=evidence_type.value,
        image=contenido,
        content_type=photo.content_type or "",
        original_filename=photo.filename,
        actor_user_id=current_user.id,
    )

    return OdometerPhotoResult(
        evidence=OdometerEvidenceRead.model_validate(evidencia),
        ocr_suggestion=sugerencia,
    )


@router.get("/evidence/{evidence_id}/photo")
async def download_photo(
    evidence_id: int,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> Response:
    """Devuelve la foto, y sólo a quien es dueño de esa jornada.

    Sin URL pública ni permanente: cada descarga vuelve a comprobar tenant y
    propiedad. Una foto de odómetro puede mostrar matrícula y kilometraje real.
    """
    evidencia = await OdometerEvidenceDAO.get_for_owner(
        evidence_id=evidence_id, company_id=company.id, user_id=current_user.id
    )
    if evidencia is None or evidencia.storage_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found"
        )

    from app.core.storage.base import get_storage
    from app.core.storage.scanning import ScanVerdict

    # Cinturón y tirantes. Una foto rechazada por el escáner no llega a
    # guardarse, así que esta rama no debería alcanzarse nunca — y precisamente
    # por eso se escribe: si algún día un camino nuevo guardara una, no se
    # serviría. El control no depende de que nadie se equivoque más arriba.
    if evidencia.scan_status == ScanVerdict.REJECTED.value:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found"
        )

    try:
        contenido = get_storage().open(evidencia.storage_key)
    except FileNotFoundError:
        # La foto se capturó y ya no está. Ocurre por dos motivos que el
        # servidor no puede distinguir: la retención la retiró, o el disco del
        # contenedor se recicló. En los dos casos es un hecho sobre el recurso,
        # no un fallo del servidor, y 410 es lo que lo dice — un 500 haría
        # pensar en una avería y un 404 negaría que la evidencia existe, que sí
        # existe y conserva su lectura confirmada.
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                "The photo is no longer stored. The confirmed reading remains "
                "on the record."
            ),
        ) from None

    return Response(
        content=contenido,
        media_type=evidencia.content_type or "application/octet-stream",
        headers={"Cache-Control": "private, no-store"},
    )


@router.post("/sessions/{work_session_id}/{evidence_type}/confirm")
async def confirm_reading(
    work_session_id: int,
    evidence_type: OdometerEvidenceType,
    payload: OdometerReadingConfirm,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> OdometerEvidenceRead:
    """El supervisor confirma o corrige la lectura.

    Con foto queda como evidencia fotográfica. Sin foto sólo se llega aquí con
    una excepción aprobada, y entonces queda marcada como manual para siempre.
    """
    await _jornada_propia(
        company_id=company.id, user_id=current_user.id, work_session_id=work_session_id
    )

    evidencia = await OdometerService.confirm_reading(
        company_id=company.id,
        work_session_id=work_session_id,
        evidence_type=evidence_type.value,
        reading=payload.reading,
        actor_user_id=current_user.id,
    )
    return OdometerEvidenceRead.model_validate(evidencia)


@router.post("/sessions/{work_session_id}/end/withdraw")
async def withdraw_end(
    work_session_id: int,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> OdometerSessionState:
    """`Keep working`: retira la lectura de cierre que `End Work` dejó pedida.

    Devuelve el estado resultante para que la pantalla decida la fase con lo
    que el servidor ya sabe, sin una segunda lectura.
    """
    await _jornada_propia(
        company_id=company.id, user_id=current_user.id, work_session_id=work_session_id
    )

    await OdometerService.withdraw_end(
        company_id=company.id,
        work_session_id=work_session_id,
        actor_user_id=current_user.id,
    )

    inicio, fin, distancia = await OdometerService.session_state(
        company_id=company.id, work_session_id=work_session_id
    )
    return OdometerSessionState(
        start=OdometerEvidenceRead.model_validate(inicio),
        end=OdometerEvidenceRead.model_validate(fin) if fin else None,
        odometer_distance=distancia,
    )


@router.post("/sessions/{work_session_id}/{evidence_type}/exception")
async def request_exception(
    work_session_id: int,
    evidence_type: OdometerEvidenceType,
    payload: OdometerExceptionCreate,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    autoaprueba: bool = Depends(
        has_permissions(["route.odometer.selfapprove"])
    ),
    company: TenantContext = Depends(get_company_required),
) -> OdometerExceptionRead:
    """Pide permiso para teclear sin foto, y a veces se lo concede solo.

    `has_permissions` **informa**, no corta: pedir la excepcion es legitimo
    para cualquiera que ejecute su jornada, y lo unico que cambia segun la
    capacidad es si hay que esperar a un administrador. Cortar aqui dejaria
    sin excepcion a quien no la tiene, que es justo el flujo que se conserva.

    La decision la toma el servidor con el permiso real del usuario; el
    cliente no envia nada que diga si puede autoaprobarse.
    """
    await _jornada_propia(
        company_id=company.id, user_id=current_user.id, work_session_id=work_session_id
    )

    solicitud = await OdometerService.request_exception(
        company_id=company.id,
        work_session_id=work_session_id,
        evidence_type=evidence_type.value,
        reason=payload.reason.value,
        reason_note=payload.reason_note,
        actor_user_id=current_user.id,
        auto_approve=autoaprueba,
    )
    return OdometerExceptionRead.model_validate(solicitud)


# ── Administración ──────────────────────────────────────────────────────────


@router.get("/exceptions/pending")
async def list_pending_exceptions(
    _authz: None = Depends(require_permissions(["route.records.adjust"])),
    company: TenantContext = Depends(get_company_required),
) -> list[OdometerExceptionQueueRead]:
    """La cola del administrador, lo más antiguo primero."""
    filas = await OdometerExceptionRequestsDAO.list_pending(company_id=company.id)
    return [
        OdometerExceptionQueueRead(
            **OdometerExceptionRead.model_validate(fila["request"]).model_dump(),
            requested_by_name=fila["requested_by_name"],
            vehicle_unit=fila["vehicle_unit"],
            time_zone=fila["time_zone"],
            utc_offset_minutes=fila["utc_offset_minutes"],
        )
        for fila in filas
    ]


@router.post("/exceptions/{request_id}/approve")
async def approve_exception(
    request_id: int,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.records.adjust"])),
    company: TenantContext = Depends(get_company_required),
) -> OdometerExceptionRead:
    """Autoriza **una** entrada manual, para esa jornada y ese extremo.

    No escribe ninguna lectura: abre la puerta para que el supervisor teclee la
    suya, y se consume al usarla.
    """
    solicitud = await OdometerService.decide_exception(
        company_id=company.id,
        request_id=request_id,
        approve=True,
        actor_user_id=current_user.id,
    )
    return OdometerExceptionRead.model_validate(solicitud)


@router.post("/exceptions/{request_id}/reject")
async def reject_exception(
    request_id: int,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.records.adjust"])),
    company: TenantContext = Depends(get_company_required),
) -> OdometerExceptionRead:
    """Rechaza y exige foto. El viaje sigue bloqueado hasta que haya evidencia."""
    solicitud = await OdometerService.decide_exception(
        company_id=company.id,
        request_id=request_id,
        approve=False,
        actor_user_id=current_user.id,
    )
    return OdometerExceptionRead.model_validate(solicitud)
