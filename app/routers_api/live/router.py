"""
API de Today / Live.

Una sola lectura y ninguna escritura
-------------------------------------
Toda la pantalla cabe en una respuesta. No es comodidad: la vista se refresca
sola cada treinta segundos, y reconstruirla desde cinco endpoints multiplicaría
ese tráfico y obligaría al navegador a recomponer reglas que son del dominio —
qué significa "On Route", qué millas cuentan, qué día es hoy.

Quién puede leer esto
----------------------
`route.live.read`, y el **alcance lo decide el servidor**. Hoy devuelve todos los
supervisores activos de la compañía; cuando exista jerarquía organizativa será
el modelo de lectura el que estreche ese conjunto, sin que la pantalla cambie.
El frontend no filtra por rol ni por nombre de rol: no sabría hacerlo con
autoridad y adivinarlo sería inventar una jerarquía que nadie aprobó.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends

from app.routers_api.users.permissions import require_permissions
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.live import dao
from app.routers_api.live.schemas import LiveSummary, LiveSupervisor, LiveToday

router = APIRouter(prefix="/live", tags=["Route · Today / Live"])


@router.get("/today", response_model=LiveToday)
async def get_today(
    _authz: None = Depends(require_permissions(["route.live.read"])),
    company: TenantContext = Depends(get_company_required),
) -> LiveToday:
    """El estado operativo de la compañía para el día de negocio en curso.

    `company` sale del subdominio, nunca del cliente: un identificador de
    compañía en la petición sería una autoridad que el navegador no tiene.
    """
    ahora = datetime.now(timezone.utc)
    filas = await dao.today_rows(company.id, ahora)

    supervisores = [LiveSupervisor(**fila) for fila in filas]
    # Sólo por compatibilidad del contrato (ver `LiveToday.session_date`).
    dias = Counter(
        s.session_date
        for s in supervisores
        if s.session_date is not None and s.time_zone_determined
    )
    dia = dias.most_common(1)[0][0] if dias else ahora.date()
    trabajando = [s for s in supervisores if s.status not in ("ended", "not_started")]

    return LiveToday(
        session_date=dia,
        generated_at=ahora,
        summary=LiveSummary(
            supervisors_working=len(trabajando),
            supervisors_total=len(supervisores),
            total_miles=sum(
                (s.official_miles for s in supervisores), Decimal("0")
            ).quantize(Decimal("0.1")),
            on_route=len([s for s in supervisores if s.status == "route"]),
            in_activity=len([s for s in supervisores if s.status == "activity"]),
        ),
        supervisors=supervisores,
    )
