"""
Los correos de actividad con **datos reales** (RTE-MAIL-CP4-01/02).

Una sola función, `generar`, sirve a la vista previa real («Generate report»),
al envío manual («Send now») y al envío automático (programador interno y cron
de DigitalOcean). No hay un segundo motor: las plantillas son las guardadas, los
números salen de Reports (`reports.dao.hechos`, `strategic.construir`) y el
alcance de la jerarquía de `organization.scope`.

La ventana de cada correo (RTE-MAIL-CLOSE-01)
---------------------------------------------
* **T1 y T3, mediodía**: corte fijo a las **12:00 locales** del destinatario
  en el día operativo, aunque se genere más tarde. Antes de las 12:00 sólo hay
  una vista *parcial* «hasta ahora», que no se envía.
* **T2, fin de jornada motivacional**: cuando **todas** las jornadas de la
  persona de ese día están cerradas; vence **20 min** después del último
  cierre. Si vuelve a abrir una jornada ese día, deja de estar cerrado y el
  vencimiento se aplaza solo (se calcula del estado actual, no de una foto).
* **T4, cierre estratégico**: **a las 19:00 locales**, siempre. No se adelanta
  aunque el equipo haya cerrado ni se retrasa por jornadas abiertas: es una
  foto de las 19:00 que dice quién sigue «En curso».

Lo que se ve en un corte es lo que se sabía en ese instante
(`strategic._al_corte` y `_completadas`): nada de lo que terminó o se midió
después.

La zona horaria
---------------
La del destinatario (`worksessions.time_zones.zonas_de_referencia`: la que fije
un administrador o la de su jornada más reciente); si no tiene, la **zona
operativa de la compañía** (`company.operational_time_zone`, en el perfil de la
compañía). Si tampoco hay, `configuration_required`: nunca UTC ni la zona más
frecuente del equipo.

Lo que nunca sale
-----------------
Notas reales (`strategic.nota_para_correo`), ubicaciones, millas y coste en los
motivacionales, ni la actividad de nadie fuera del alcance.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.db.session import db_session
from app.routers_api.activityemails import content, strategic
from app.routers_api.activityemails.content import ActivityEmailType
from app.routers_api.activityemails.service import ActivityEmailService
from app.routers_api.companies.models import Company
from app.routers_api.reports import dao as reports_dao
from app.routers_api.users.models import Users
from app.routers_api.worksessions.models import WorkSession, WorkSessionStatus
from app.routers_api.worksessions.time_zones import zona_valida, zonas_de_referencia

MEDIODIA = time(12, 0)
#: La hora del cierre estratégico (T4), local del destinatario.
CIERRE_ESTRATEGICO = time(19, 0)
TRAS_EL_CIERRE = timedelta(minutes=20)

MOTIVACIONALES = {ActivityEmailType.MIDDAY_MOTIVATION.value, ActivityEmailType.END_OF_DAY_RECOGNITION.value}
DE_MEDIODIA = {ActivityEmailType.MIDDAY_MOTIVATION.value, ActivityEmailType.STRATEGIC_MIDDAY_REPORT.value}

#: Cómo se nombra cada categoría en los correos motivacionales (singular, plural).
_CATEGORIAS: dict[str, tuple[str, str]] = {
    "client_visit": ("visita a cliente", "visitas a clientes"),
    "employee_visit": ("visita a empleado", "visitas a empleados"),
    "recruiting": ("actividad de reclutamiento", "actividades de reclutamiento"),
    "check_delivery": ("entrega", "entregas"),
    "office": ("gestión de oficina", "gestiones de oficina"),
    "other": ("otra actividad", "otras actividades"),
}
_GENERAL: dict[str, str] = {
    "client_visit": "visitas",
    "employee_visit": "visitas",
    "recruiting": "reclutamiento",
    "check_delivery": "entregas",
    "office": "gestiones operativas",
    "other": "otras actividades",
}


@dataclass
class ReporteReal:
    report_type: str
    recipient_user_id: int
    recipient_name: str
    operational_date: date
    generated_at: datetime
    time_zone: str | None
    #: Fin de la ventana de datos.
    cutoff_at: datetime | None
    #: Cuándo toca enviarlo (`None`: todavía no se sabe).
    due_at: datetime | None
    #: `True` mientras la ventana no está cerrada (vista «hasta ahora»).
    provisional: bool
    #: `True` si, por datos, hay correo que mandar (actividad, equipo).
    eligible: bool
    #: Por qué no es elegible o no es final: código fijo.
    reason_code: str | None
    #: Personas cubiertas (estratégicos).
    coverage: int | None
    #: Actividades del día dentro de la ventana.
    activity_count: int
    subject: str | None
    body: str | None
    template_version: int


def _local(dia: date, hora: time, zona: str) -> datetime:
    """La hora local `hora` de `dia` en `zona`, como instante. 12:00 nunca es
    ambigua en un cambio de horario, así que no hay que elegir pliegue."""
    return datetime.combine(dia, hora, tzinfo=ZoneInfo(zona))


async def zona_del_destinatario(company_id: int, user_id: int) -> str | None:
    """La suya; si no, la operativa de la compañía; si no, `None`."""
    propia = (await zonas_de_referencia(company_id=company_id, user_ids=[user_id])).get(user_id, (None, None))[0]
    if propia:
        return propia
    async with db_session() as session:
        return zona_valida(
            await session.scalar(select(Company.operational_time_zone).where(Company.id == company_id))
        )


async def _persona(user_id: int) -> tuple[str, str]:
    async with db_session() as session:
        fila = (
            await session.execute(select(Users.first_name, Users.last_name).where(Users.id == user_id))
        ).first()
    if fila is None:
        return "", ""
    return fila.first_name or "", f"{fila.first_name or ''} {fila.last_name or ''}".strip()


async def _jornadas_del_dia(company_id: int, user_ids: list[int], dia: date) -> list:
    if not user_ids:
        return []
    async with db_session() as session:
        return (
            await session.execute(
                select(WorkSession.user_id, WorkSession.status, WorkSession.ended_at).where(
                    WorkSession.company_id == company_id,
                    WorkSession.user_id.in_(user_ids),
                    WorkSession.session_date == dia,
                )
            )
        ).all()


def _cierre(jornadas: list) -> tuple[bool, datetime | None]:
    """(todas cerradas, último cierre) de unas jornadas."""
    if not jornadas:
        return False, None
    if any(j.status != WorkSessionStatus.ENDED.value or j.ended_at is None for j in jornadas):
        return False, None
    return True, max(j.ended_at for j in jornadas)


# ── Bloques de los correos motivacionales ──────────────────────────────────


def _completadas(filas: list[dict], hasta: datetime | None) -> list[dict]:
    return [
        f for f in filas
        if f["execution_id"] is not None
        and f["activity_ended_at"] is not None
        and (hasta is None or f["activity_ended_at"] <= hasta)
        and f["purpose"] in _CATEGORIAS
    ]


def _abiertas(filas: list[dict], hasta: datetime) -> list[dict]:
    """Iniciadas antes del corte y sin finalizar en ese instante."""
    return [
        f for f in filas
        if f["execution_id"] is not None
        and f["activity_started_at"] is not None
        and f["activity_started_at"] < hasta
        and (f["activity_ended_at"] is None or f["activity_ended_at"] > hasta)
        and f["purpose"] in _CATEGORIAS
    ]


def _lineas_de_abiertas(abiertas: list[dict], corte: datetime, cierres: dict[int, datetime | None]) -> list[str]:
    """«En curso» si **su** jornada seguía abierta en el corte; si ya había
    cerrado, «sin finalizar»: no se afirma que siga en ejecución."""
    en_curso = sum(1 for f in abiertas if (c := cierres.get(f["session_id"])) is None or c > corte)
    sin_finalizar = len(abiertas) - en_curso
    lineas = []
    if en_curso:
        lineas.append(f"- {en_curso} {'actividad en curso' if en_curso == 1 else 'actividades en curso'}.")
    if sin_finalizar:
        lineas.append(
            f"- {sin_finalizar} "
            f"{'actividad iniciada sin finalizar' if sin_finalizar == 1 else 'actividades iniciadas sin finalizar'}."
        )
    return lineas


def _lineas(filas: list[dict]) -> list[str]:
    cuenta = Counter(f["purpose"] for f in filas)
    return [
        f"- {n} {(_CATEGORIAS[p][0] if n == 1 else _CATEGORIAS[p][1])}."
        for p in _CATEGORIAS if (n := cuenta.get(p))
    ]


def _semana(filas: list[dict]) -> str:
    total = len(filas)
    generales = []
    for p in _CATEGORIAS:
        if any(f["purpose"] == p for f in filas) and _GENERAL[p] not in generales:
            generales.append(_GENERAL[p])
    if not total:
        return "Tu semana hasta hoy:\nSin actividades completadas registradas esta semana."
    que = generales[0] if len(generales) == 1 else ", ".join(generales[:-1]) + " y " + generales[-1]
    palabra = "actividad realizada" if total == 1 else "actividades realizadas"
    return f"Tu semana hasta hoy:\n{total} {palabra} durante la semana en {que}."


# ── El generador ──────────────────────────────────────────────────────────


async def generar(
    *, company_id: int, report_type: str, recipient_user_id: int, operational_date: date, ahora: datetime
) -> ReporteReal:
    tipo = ActivityEmailType(report_type).value
    plantilla = await ActivityEmailService.get_template(company_id=company_id, template_type=tipo)
    nombre_de_pila, nombre = await _persona(recipient_user_id)
    base = dict(
        report_type=tipo,
        recipient_user_id=recipient_user_id,
        recipient_name=nombre,
        operational_date=operational_date,
        generated_at=ahora,
        template_version=plantilla["version"],
    )

    def sin_correo(zona, corte, vence, provisional, motivo, cobertura=None, actividades=0):
        return ReporteReal(
            **base, time_zone=zona, cutoff_at=corte, due_at=vence, provisional=provisional,
            eligible=False, reason_code=motivo, coverage=cobertura, activity_count=actividades,
            subject=None, body=None,
        )

    def con_correo(zona, corte, vence, provisional, motivo, valores, cobertura=None, actividades=0):
        return ReporteReal(
            **base, time_zone=zona, cutoff_at=corte, due_at=vence, provisional=provisional,
            eligible=True, reason_code=motivo, coverage=cobertura, activity_count=actividades,
            subject=content.render(plantilla["subject"], valores),
            body=content.render(plantilla["body"], valores),
        )

    lunes = strategic.lunes_de(operational_date)

    zona = await zona_del_destinatario(company_id, recipient_user_id)

    # ── Motivacionales: la propia actividad, sin notas ni ubicaciones ──
    if tipo in MOTIVACIONALES:
        if zona is None:
            return sin_correo(None, None, None, True, "configuration_required")
        if tipo == ActivityEmailType.MIDDAY_MOTIVATION.value:
            mediodia = _local(operational_date, MEDIODIA, zona)
            provisional = ahora < mediodia
            corte = ahora if provisional else mediodia
            vence = mediodia
        else:
            jornadas = await _jornadas_del_dia(company_id, [recipient_user_id], operational_date)
            if not jornadas:
                return sin_correo(zona, None, None, False, "no_workday")
            cerrada, ultimo = _cierre(jornadas)
            provisional = not cerrada
            corte = ahora if provisional else ultimo
            vence = None if provisional else ultimo + TRAS_EL_CIERRE
        filas = await reports_dao.hechos(
            company_id=company_id, user_ids=[recipient_user_id], inicio=lunes, fin=operational_date
        )
        del_dia = [f for f in filas if f["session_date"] == operational_date]
        hoy = _completadas(del_dia, corte)
        al_corte = _abiertas(del_dia, corte)
        motivo = "partial_window" if provisional else None
        # Mediodía sale con al menos una actividad iniciada antes del corte,
        # terminada o no; fin de jornada sigue pidiendo una finalizada. Las
        # iniciadas sin finalizar se cuentan aparte, nunca como hechas.
        if tipo == ActivityEmailType.MIDDAY_MOTIVATION.value:
            sin_actividad = not hoy and not al_corte
        else:
            sin_actividad = not hoy
        if sin_actividad:
            return sin_correo(zona, corte, vence, provisional, "no_activity")
        abiertas = _lineas_de_abiertas(
            al_corte, corte, await strategic._cierres(company_id, {f["session_id"] for f in al_corte})
        )
        valores = {"user_first_name": nombre_de_pila or "colega"}
        if tipo == ActivityEmailType.MIDDAY_MOTIVATION.value:
            valores["midday_activity_block"] = "Hasta ahora has realizado:\n" + "\n".join(_lineas(hoy) + abiertas)
        else:
            valores["day_activity_block"] = "Tu día en resumen:\n" + "\n".join(_lineas(hoy) + abiertas)
            valores["week_activity_block"] = _semana(_completadas(filas, corte))
        return con_correo(zona, corte, vence, provisional, motivo, valores, actividades=len(hoy))

    # ── Estratégicos: las personas activas del alcance del destinatario ──
    _, equipo = await strategic.roster(company_id, recipient_user_id)
    if not equipo:
        return sin_correo(zona, None, None, False, "no_team", cobertura=0)
    if zona is None:
        return sin_correo(None, None, None, True, "configuration_required", cobertura=len(equipo))

    cierre = tipo == ActivityEmailType.STRATEGIC_END_OF_DAY_REPORT.value
    hora = _local(operational_date, CIERRE_ESTRATEGICO if cierre else MEDIODIA, zona)
    provisional = ahora < hora
    corte = ahora if provisional else hora
    motivo = "partial_window" if provisional else None

    reporte = await strategic.construir(
        company_id=company_id,
        manager_user_id=recipient_user_id,
        cierre=cierre,
        dia=operational_date,
        corte=corte,
        inicio_semana=lunes,
    )
    actividades = sum(f.eventos for p in reporte.personas for f in p.dia)
    valores = strategic.valores(
        reporte,
        manager_first_name=nombre_de_pila,
        generado=ahora.astimezone(ZoneInfo(zona)).strftime("%d/%m/%Y %I:%M %p"),
        con_snapshot_propio="executive_snapshot" in content.marcadores(plantilla["body"]),
    )
    vence = hora
    return con_correo(zona, corte, vence, provisional, motivo, valores, cobertura=len(reporte.personas),
                      actividades=actividades)
