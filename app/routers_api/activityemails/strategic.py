"""
Reporte estratégico de actividad para mandos (RTE-MAIL-UNIFIED-01 V1.2, CP2).

Qué produce
-----------
Para un mando, **un bloque por persona autorizada** de su equipo:

1. Cabecera: nombre y cargo (nada más: ni correo, ni teléfono, ni referencias).
2. *Activity Breakdown* del día: Activity · Events · Miles · Time · Est. Cost.
3. *Activity Details* del día, en orden: categoría, horas, duración, estado y
   la nota **sólo si está aprobada para correo**.
4. Sólo en el cierre: el acumulado semanal de la persona por categoría.

Y, **sólo en el cierre y después de todas las personas**, un único *Team
Weekly Summary*: personas con actividad registrada, actividades, millas,
tiempo y coste, y las mismas categorías.

De dónde salen los números
--------------------------
De **los mismos contratos que Reports** (`reports.dao.hechos` y
`reports.service._metricas`): una fila por viaje con su bloque de actividad,
las millas oficiales, el tiempo de bloques terminados y el coste estimado por
jornada. Aquí no se recalcula nada. El conjunto de personas se decide **una
vez** con `organization.scope.alcance_administrativo` —el mismo alcance de
Activity y Reports: el CEO ve la rama de Sales y el COO no—, sin el propio
mando, y se usa igual para las secciones individuales y para el total del
equipo.

El total del equipo es **la suma de lo que se enseña** en cada sección
individual (millas ya redondeadas por persona, segundos, eventos, céntimos):
así cuadra en el mismo correo. Las filas son una por viaje, y cada persona sale
una vez, así que no hay doble conteo aunque alguien cuelgue de varios niveles.

Lo que está pendiente y no se decide aquí
-----------------------------------------
* **DP-NOTES:** ninguna nota real sale por correo. `nota_para_correo` devuelve
  «Detalle no incluido en el correo» si hay nota y «Sin notas registradas» si
  no. Sólo los datos de demostración llevan notas, y son ficticias.
* **DP-TIMEZONE / DP-WEEK / DP-CUTOFF:** el día, el corte del mediodía y el
  inicio de semana los **pasa quien llama**; aquí no se elige ningún valor. La
  semana empieza el lunes como en Activity, y el informe lo rotula.

Texto plano, sin HTML: lo mismo que el resto de correos de la aplicación.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.db.session import db_session
from app.core.rbac.catalog import ROUTE_PRODUCT_ROLE_LABELS
from app.routers_api.companies.models import UserCompany
from app.routers_api.fuelreference.service import CALCULATED
from app.routers_api.organization.scope import alcance_administrativo, condicion_de_jornadas
from app.routers_api.reports import dao as reports_dao
from app.routers_api.reports.excel import duracion, reloj
from app.routers_api.reports.service import (
    PROPOSITOS_V07,
    _combustible_por_jornada,
    _enriquecer,
    _metricas,
)
from app.routers_api.roles.models import Role
from app.routers_api.users.models import Users
from app.routers_api.worksessions.models import WorkSession

CATEGORIAS: dict[str, str] = {
    "client_visit": "Client Visit",
    "employee_visit": "Employee Visit",
    "recruiting": "Recruiting",
    "check_delivery": "Check Delivery",
    "office": "Office",
    "other": "Other",
}

#: El estado de coste de un corte con sólo algunas jornadas calculadas
#: (`reports.service._estado`).
PARCIAL = "partial"

NO_DISPONIBLE = "No disponible"
SIN_NOTAS = "Sin notas registradas"
NOTA_RETENIDA = "Detalle no incluido en el correo"
SIN_ACTIVIDAD = "Sin actividades registradas para el período"
SIN_PERSONAS = "Sin personas autorizadas para el reporte"


def nota_para_correo(nota: str | None) -> str:
    """DP-NOTES: una nota real **nunca** sale por correo hasta que se apruebe."""
    return NOTA_RETENIDA if nota and nota.strip() else SIN_NOTAS


# ══ Modelo ═══════════════════════════════════════════════════════════════════


@dataclass
class Fila:
    """Una fila de desglose: una categoría o el total."""

    actividad: str
    eventos: int
    millas: Decimal | None
    segundos: int
    #: `None` = no disponible. `parcial` = sólo algunas jornadas tienen coste.
    coste: Decimal | None
    parcial: bool = False
    en_curso: bool = False


@dataclass
class Detalle:
    categoria: str
    dia: date
    inicio: str
    fin: str
    duracion: str
    estado: str
    nota: str


@dataclass
class Persona:
    user_id: int
    nombre: str
    cargo: str
    dia: list[Fila] = field(default_factory=list)
    detalles: list[Detalle] = field(default_factory=list)
    semana: list[Fila] = field(default_factory=list)


@dataclass
class Reporte:
    cierre: bool
    dia: date
    inicio_semana: date
    personas: list[Persona]


# ══ Render ═══════════════════════════════════════════════════════════════════


def _millas(f: Fila) -> str:
    return NO_DISPONIBLE if f.millas is None else f"{f.millas:.1f}"


def _tiempo(f: Fila) -> str:
    if not f.eventos:
        return "—"
    texto = duracion(f.segundos) or "0m"
    return f"{texto} (+ en curso)" if f.en_curso else texto


def _coste(f: Fila) -> str:
    if f.coste is None:
        return NO_DISPONIBLE
    return f"${f.coste:,.2f}" + (" (parcial)" if f.parcial else "")


def _tabla(filas: list[Fila], *, titulo_eventos: str = "Events") -> list[str]:
    cabecera = f"{'Activity':<16}{titulo_eventos:>8}{'Miles':>10}  {'Time':<20}{'Est. Cost':>14}"
    lineas = [cabecera, "-" * len(cabecera)]
    for f in filas:
        lineas.append(
            f"{f.actividad:<16}{f.eventos:>8}{_millas(f):>10}  {_tiempo(f):<20}{_coste(f):>14}"
        )
    return lineas


def _total(filas: list[Fila], nombre: str = "TOTAL") -> Fila:
    """Suma de lo que se enseña: cuadra con las filas por construcción."""
    millas = [f.millas for f in filas]
    costes = [f.coste for f in filas]
    return Fila(
        actividad=nombre,
        eventos=sum(f.eventos for f in filas),
        millas=None if any(m is None for m in millas) else sum(millas, Decimal("0")),
        segundos=sum(f.segundos for f in filas),
        coste=None if all(c is None for c in costes) else sum((c for c in costes if c is not None), Decimal("0")),
        parcial=any(c is None for c in costes) or any(f.parcial for f in filas),
        en_curso=any(f.en_curso for f in filas),
    )


def render_personas(reporte: Reporte) -> str:
    if not reporte.personas:
        return SIN_PERSONAS
    bloques: list[str] = []
    for p in reporte.personas:
        lineas = [f"■ {p.nombre} · {p.cargo}", ""]
        lineas.append(f"Activity Breakdown — {reporte.dia:%d/%m/%Y}")
        lineas += _tabla([*p.dia, _total(p.dia)]) if p.dia else [SIN_ACTIVIDAD]
        lineas += ["", "Activity Details"]
        if p.detalles:
            for d in p.detalles:
                horas = f"{d.inicio}–{d.fin}" if d.fin else f"{d.inicio}–"
                lineas.append(f"• {d.categoria} | {horas} | {d.duracion or '—'} | {d.estado}")
                lineas.append(f"  Notas: {d.nota}")
        else:
            lineas.append(SIN_ACTIVIDAD)
        if reporte.cierre:
            lineas += ["", f"Weekly Activity Summary — {reporte.inicio_semana:%d/%m} a {reporte.dia:%d/%m/%Y}"]
            lineas += _tabla([*p.semana, _total(p.semana)], titulo_eventos="Week") if p.semana else [SIN_ACTIVIDAD]
        bloques.append("\n".join(lineas))
    return "\n\n".join(bloques)


def resumen_del_equipo(reporte: Reporte) -> tuple[int, list[Fila]]:
    """Personas con actividad y filas por categoría: sumas de las secciones."""
    con_actividad = [p for p in reporte.personas if any(f.eventos for f in p.semana)]
    filas: list[Fila] = []
    for clave, etiqueta in CATEGORIAS.items():
        de_la_categoria = [f for p in reporte.personas for f in p.semana if f.actividad == etiqueta]
        if de_la_categoria:
            filas.append(_total(de_la_categoria, etiqueta))
    return len(con_actividad), filas


def render_equipo(reporte: Reporte) -> str:
    """El *Team Weekly Summary*: sólo cierre, una vez, después de las personas."""
    periodo = f"Semana {reporte.inicio_semana:%d/%m/%Y} - {reporte.dia:%d/%m/%Y} (corte)"
    if not reporte.personas:
        return f"Team Weekly Summary | {periodo}\n{SIN_PERSONAS}"
    personas, filas = resumen_del_equipo(reporte)
    if not filas:
        return f"Team Weekly Summary | {periodo}\n{SIN_ACTIVIDAD}"
    total = _total(filas)
    lineas = [
        f"Team Weekly Summary | {periodo}",
        f"Personas con actividad registrada en la semana: {personas}",
        f"Actividades registradas: {total.eventos} | Millas: {_millas(total)} | "
        f"Tiempo en actividades: {_tiempo(total)} | Costo estimado: {_coste(total)}",
        "(Tiempo en actividades no es la jornada pagada.)",
        "",
        *_tabla([*filas, total], titulo_eventos="Week"),
    ]
    return "\n".join(lineas)


def valores(reporte: Reporte, *, manager_first_name: str, generado: str) -> dict[str, str]:
    etiqueta = f"{reporte.dia:%d/%m/%Y}"
    vals = {
        "manager_first_name": manager_first_name or "equipo",
        "report_period_label": etiqueta,
        "report_generated_at": generado,
        "per_person_report": render_personas(reporte),
    }
    if reporte.cierre:
        vals["team_weekly_summary"] = render_equipo(reporte)
        vals["week_period_label"] = f"{reporte.inicio_semana:%d/%m/%Y} - {etiqueta}"
    return vals


# ══ Demostración: jerarquía, actividad y notas **ficticias** ═════════════════

_DEMO_DIA = date(2026, 10, 14)
_DEMO_LUNES = date(2026, 10, 12)


def _demo(cierre: bool) -> Reporte:
    ana = Persona(
        user_id=-1,
        nombre="Ana Ejemplo",
        cargo="Supervisor",
        dia=[
            Fila("Client Visit", 2, Decimal("18.4"), 5400, Decimal("7.12")),
            Fila("Recruiting", 1, Decimal("6.2"), 2700, Decimal("2.40")),
        ],
        detalles=[
            Detalle("Client Visit", _DEMO_DIA, "8:10 AM", "9:25 AM", "1h 15m", "Finalizada",
                    "Revisión de turnos con el cliente ficticio Alfa."),
            Detalle("Recruiting", _DEMO_DIA, "9:50 AM", "10:35 AM", "45m", "Finalizada", SIN_NOTAS),
            Detalle("Client Visit", _DEMO_DIA, "11:05 AM", "11:20 AM", "15m", "Finalizada",
                    "Entrega de documentación de ejemplo."),
        ],
    )
    luis = Persona(
        user_id=-2,
        nombre="Luis Muestra",
        cargo="OSM",
        dia=[
            Fila("Office", 1, Decimal("4.0"), 3600, None),
            Fila("Employee Visit", 1, Decimal("9.5"), 0, None, en_curso=True),
        ],
        detalles=[
            Detalle("Office", _DEMO_DIA, "8:30 AM", "9:30 AM", "1h 00m", "Finalizada",
                    "Reunión de coordinación de prueba."),
            Detalle("Employee Visit", _DEMO_DIA, "11:40 AM", "", "", "En curso", SIN_NOTAS),
        ],
    )
    if cierre:
        ana.dia.append(Fila("Office", 1, Decimal("3.1"), 1800, Decimal("1.20")))
        ana.detalles.append(
            Detalle("Office", _DEMO_DIA, "2:10 PM", "2:40 PM", "30m", "Finalizada", SIN_NOTAS)
        )
        luis.dia[1] = Fila("Employee Visit", 1, Decimal("9.5"), 2400, None)
        luis.detalles[1] = Detalle(
            "Employee Visit", _DEMO_DIA, "11:40 AM", "12:20 PM", "40m", "Finalizada",
            "Visita de seguimiento ficticia.",
        )
        ana.semana = [
            Fila("Client Visit", 6, Decimal("71.6"), 20700, Decimal("27.70")),
            Fila("Recruiting", 3, Decimal("22.0"), 8100, Decimal("8.50")),
            Fila("Office", 2, Decimal("8.3"), 4200, Decimal("3.20")),
        ]
        luis.semana = [
            Fila("Client Visit", 2, Decimal("30.2"), 6000, None),
            Fila("Employee Visit", 3, Decimal("27.9"), 7800, None),
            Fila("Office", 2, Decimal("8.0"), 7200, None),
        ]
    return Reporte(cierre=cierre, dia=_DEMO_DIA, inicio_semana=_DEMO_LUNES, personas=[ana, luis])


def valores_de_demostracion(cierre: bool) -> dict[str, str]:
    return valores(_demo(cierre), manager_first_name="Carla", generado="14/10/2026 12:00 PM (ejemplo)")


# ══ Datos reales (para el envío programado, CP4; sin uso para enviar hoy) ════


async def _personas_del_equipo(company_id: int, manager_user_id: int):
    alcance = await alcance_administrativo(company_id=company_id, actor_user_id=manager_user_id)
    if alcance.tenant:
        # Sin cargo de mando no hay equipo: no se reporta la compañía entera.
        return alcance, []
    ids = sorted(alcance.actuales - {manager_user_id})
    if not ids:
        return alcance, []
    async with db_session() as session:
        filas = (
            await session.execute(
                select(Users.id, Users.first_name, Users.last_name, Role.name)
                .join(UserCompany, UserCompany.user_id == Users.id)
                .join(Role, Role.id == UserCompany.role_id)
                .where(
                    UserCompany.company_id == company_id,
                    UserCompany.deleted_at.is_(None),
                    Users.id.in_(ids),
                )
                .order_by(Users.first_name, Users.last_name, Users.id)
            )
        ).all()
    return alcance, [
        (f.id, f"{f.first_name or ''} {f.last_name or ''}".strip() or f"User {f.id}",
         ROUTE_PRODUCT_ROLE_LABELS.get(f.name, f.name))
        for f in filas
    ]


def _filas_por_categoria(filas: list[dict], combustible: dict) -> list[Fila]:
    salida = []
    for clave in PROPOSITOS_V07:
        dentro = [f for f in filas if f["purpose"] == clave]
        if not dentro:
            continue
        m = _metricas(dentro, combustible)
        sin_coste = m["fuel_cost_status"] not in (CALCULATED, PARCIAL)
        salida.append(
            Fila(
                actividad=CATEGORIAS[clave],
                eventos=m["activities"],
                millas=m["official_miles"],
                segundos=m["activity_seconds"],
                coste=None if sin_coste else m["estimated_fuel_cost"],
                parcial=m["fuel_cost_status"] == PARCIAL,
                en_curso=m["has_open_activity"],
            )
        )
    return salida


def _detalle(f: dict) -> Detalle:
    terminado = f["activity_ended_at"] is not None
    if terminado:
        estado = "Finalizada"
    elif f["session_ended"]:
        estado = "Sin cierre registrado"
    else:
        estado = "En curso"
    return Detalle(
        categoria=CATEGORIAS.get(f["purpose"], f["purpose"]),
        dia=f["session_date"],
        inicio=reloj(f["activity_started_at"], f["time_zone"], f["utc_offset_minutes"]),
        fin=reloj(f["activity_ended_at"], f["time_zone"], f["utc_offset_minutes"]) if terminado else "",
        duracion=duracion(f["segundos"]) if terminado else "",
        estado=estado,
        nota=nota_para_correo(f["notes"]),
    )


async def construir(
    *,
    company_id: int,
    manager_user_id: int,
    cierre: bool,
    dia: date,
    corte: datetime | None,
    inicio_semana: date,
) -> Reporte:
    """El reporte con datos reales, **sin notas reales** (DP-NOTES).

    `dia` (día de negocio), `corte` (fin del mediodía) e `inicio_semana` los
    decide quien llama: zona horaria, hora de corte e inicio de semana son
    decisiones pendientes del PO. Sólo lectura.
    """
    alcance, personas = await _personas_del_equipo(company_id, manager_user_id)
    reporte = Reporte(cierre=cierre, dia=dia, inicio_semana=inicio_semana, personas=[])
    if not personas:
        return reporte
    ids = [p[0] for p in personas]
    jornadas = condicion_de_jornadas(alcance, WorkSession.user_id, WorkSession.started_at)
    desde = inicio_semana if cierre else dia
    filas = await reports_dao.hechos(
        company_id=company_id, user_ids=ids, inicio=desde, fin=dia, jornadas=jornadas
    )
    if corte is not None:
        filas = [f for f in filas if f["trip_started_at"] is None or f["trip_started_at"] < corte]
    combustible = await _combustible_por_jornada(company_id, filas)
    for f in filas:
        _enriquecer(f, combustible[f["session_id"]])

    for user_id, nombre, cargo in personas:
        propias = [f for f in filas if f["user_id"] == user_id]
        hoy = [f for f in propias if f["session_date"] == dia]
        reporte.personas.append(
            Persona(
                user_id=user_id,
                nombre=nombre,
                cargo=cargo,
                dia=_filas_por_categoria(hoy, combustible),
                detalles=[
                    _detalle(f)
                    for f in sorted(
                        (f for f in hoy if f["execution_id"] is not None),
                        key=lambda f: (f["activity_started_at"], f["execution_id"]),
                    )
                ],
                semana=_filas_por_categoria(propias, combustible) if cierre else [],
            )
        )
    return reporte


def lunes_de(dia: date) -> date:
    """El lunes de la semana de `dia` (DP-WEEK: la regla de Activity, pendiente de confirmar)."""
    return dia - timedelta(days=dia.weekday())
