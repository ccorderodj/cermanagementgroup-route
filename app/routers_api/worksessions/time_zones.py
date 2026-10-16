"""
La zona horaria operativa de CER Route (T-1/T-2).

Tres datos distintos que no se confunden (TR-10)
-------------------------------------------------
* el **instante** de un evento: `timestamptz`, absoluto, no cambia nunca;
* la **fecha de jornada**: `session_date`, el día local en que empezó, congelado;
* la **hora presentada**: el instante formateado en la zona de su jornada.

Este módulo resuelve qué zona aplica. Todo lo demás la consume de aquí, para que
Start Work, Today y User Activity no tengan tres versiones de la misma regla.

Una sola zona efectiva por jornada (regla de precedencia del PO)
-----------------------------------------------------------------
1. el override del perfil, si un administrador fijó uno válido;
2. si no, la zona IANA que reportó el dispositivo al iniciar;
3. la que se aplicó se guarda en `work_session.start_time_zone`, y es la que
   fecha `session_date` **y** la que formatea sus horas.

Guardar siempre la del dispositivo cuando hay override produciría una jornada
fechada en una zona y mostrada en otra.

El «hoy» de un supervisor
-------------------------
Su override; si no tiene, la zona efectiva de **su propia** jornada más reciente
que la registró; si tampoco, **indeterminada**. Nunca la de otra persona, y
nunca un desfase histórico extrapolado: un `-240` de octubre no dice nada de una
fecha de noviembre (D3).

Por qué `zoneinfo` y la lista de `available_timezones()`
--------------------------------------------------------
Es la fuente de las reglas históricas de cambio de horario, así que validar
contra ella garantiza que toda zona aceptada se puede aplicar. `tzdata` está
declarado como dependencia explícita: sin él, `zoneinfo` no tiene base de
zonas en Windows ni en imágenes mínimas de Linux.
"""

from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

from sqlalchemy import select

from app.core.db.session import db_session

#: De dónde salió la zona de referencia de un supervisor. Viaja en el contrato
#: para que la pantalla pueda decir «zona no determinada» sin deducirlo.
ORIGEN_OVERRIDE = "override"
ORIGEN_ULTIMA_JORNADA = "last_session"
ORIGEN_INDETERMINADA = "undetermined"


@lru_cache(maxsize=1)
def _zonas_validas() -> frozenset[str]:
    return frozenset(available_timezones())


def zona_valida(nombre: str | None) -> str | None:
    """El identificador si `zoneinfo` lo reconoce; `None` si no.

    `None` y no una excepción: una zona inválida del dispositivo **no bloquea**
    Start Work (D-10). Para el override administrativo, donde sí hay que
    rechazar, el servicio convierte el `None` en un 422.
    """
    if not nombre:
        return None
    nombre = nombre.strip()
    return nombre if nombre in _zonas_validas() else None


def zona_efectiva(*, override: str | None, dispositivo: str | None) -> str | None:
    """La zona que gobierna una jornada nueva: override, si no, dispositivo."""
    return zona_valida(override) or zona_valida(dispositivo)


def dia_local(instante: datetime, zona: str) -> date:
    """La fecha del calendario de `zona` en ese instante.

    Convertir instante → hora local nunca es ambiguo, tampoco en los cambios de
    horario: cada instante tiene exactamente una hora local. La ambigüedad sólo
    aparece al revés —hora local → instante— y eso no se hace aquí.
    """
    return instante.astimezone(ZoneInfo(zona)).date()


async def zonas_de_referencia(
    *, company_id: int, user_ids: list[int]
) -> dict[int, tuple[str | None, str]]:
    """La zona con la que se calcula el «hoy» de cada supervisor, y su origen.

    Dos consultas para toda la lista, no una por persona: Today se refresca sola
    y un N+1 aquí sería carga permanente.
    """
    from app.routers_api.vehicles.models import SupervisorProfile
    from app.routers_api.worksessions.models import WorkSession

    if not user_ids:
        return {}

    async with db_session() as session:
        overrides = dict(
            (
                await session.execute(
                    select(
                        SupervisorProfile.user_id,
                        SupervisorProfile.operational_time_zone,
                    ).where(
                        SupervisorProfile.company_id == company_id,
                        SupervisorProfile.user_id.in_(user_ids),
                        SupervisorProfile.deleted_at.is_(None),
                        SupervisorProfile.operational_time_zone.is_not(None),
                    )
                )
            ).all()
        )
        # La zona efectiva de la jornada más reciente **de cada uno** que la
        # registró. Las jornadas anteriores a T-1/T-2 no la tienen y no cuentan:
        # su desfase no se extrapola a hoy.
        ultimas = dict(
            (
                await session.execute(
                    select(WorkSession.user_id, WorkSession.start_time_zone)
                    .where(
                        WorkSession.company_id == company_id,
                        WorkSession.user_id.in_(user_ids),
                        WorkSession.start_time_zone.is_not(None),
                    )
                    .distinct(WorkSession.user_id)
                    .order_by(WorkSession.user_id, WorkSession.started_at.desc())
                )
            ).all()
        )

    resultado: dict[int, tuple[str | None, str]] = {}
    for user_id in user_ids:
        override = zona_valida(overrides.get(user_id))
        if override:
            resultado[user_id] = (override, ORIGEN_OVERRIDE)
            continue
        ultima = zona_valida(ultimas.get(user_id))
        if ultima:
            resultado[user_id] = (ultima, ORIGEN_ULTIMA_JORNADA)
            continue
        resultado[user_id] = (None, ORIGEN_INDETERMINADA)
    return resultado
