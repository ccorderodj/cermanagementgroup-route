"""Registro de evidencia de ubicación y finalización de Missing (RTE06-CP2).

La frontera de §13, en un sitio
-------------------------------
Sólo se acepta evidencia que se pueda atar a la vez a: el tenant autenticado, el
supervisor autenticado, una jornada autoritativa y un evento de ciclo de vida
que **ocurrió**. Las cuatro cosas se comprueban aquí; ninguna llega del cuerpo
de la petición.

La excepción de End Work
------------------------
End Work no espera a la ubicación: la jornada pasa a `ENDED` inmediatamente. Pero
la recuperación que **ya había empezado** para ese End Work concreto puede
terminar después, y eso obliga a una grieta controlada en la frontera: la jornada
ya no está ACTIVE cuando llega ese punto.

La grieta es lo más estrecha que se pudo hacer: sólo el evento `end_work`, sólo
la jornada cuyo `ended_at` está dentro de la ventana de recuperación, y sólo para
el supervisor dueño. No puede abrir captura nueva, no reabre la jornada y no
sirve para ningún otro evento.

Por qué el 404 y no el 403
--------------------------
Un sujeto que no existe, que es de otra compañía o que es de otra jornada dan
**404** — el mismo que si no existiera. Confirmar que existe pero no es tuyo
confirma que existe (regla 8 de backend, y §31 "no arbitrary cross-user evidence
injection").
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.audit.service import record_event
from app.core.db.session import transaction
from app.core.platform.config_service import platform_config
from app.routers_api.location.dao import (
    LocationFixesDAO,
    MissingLocationEventsDAO,
    SubjectsDAO,
)
from app.routers_api.location.models import (
    LocationEventKind,
    LocationEvidenceLevel,
    LocationFix,
    MissingLocationEvent,
    MissingLocationReason,
    MissingNotificationStatus,
    subject_kind_for,
)
from app.routers_api.location.schemas import LocationEvidenceIn, MissingLocationIn
from app.routers_api.worksessions.dao import WorkSessionsDAO
from app.routers_api.worksessions.models import WorkSession, WorkSessionStatus

#: Lo que se responde cuando el sujeto no es atable. Un solo texto para los
#: cuatro motivos: distinguirlos en la respuesta sería filtrar cuál se cumplió.
_NO_ENCONTRADO = "No such lifecycle event for this work session."


def _politica() -> dict:
    return platform_config.policy("route_location")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class LocationEvidenceService:
    """Escribe evidencia de ubicación, o la ausencia de ella."""

    @staticmethod
    async def _jornada_autoritativa(
        *,
        company_id: int,
        user_id: int,
        event_kind: LocationEventKind,
        subject_id: int,
    ) -> WorkSession:
        """La jornada a la que esta evidencia puede pertenecer.

        Normalmente es la jornada ACTIVE del supervisor. La excepción es
        `end_work`: la jornada ya está `ENDED` y aun así la recuperación de ese
        End Work puede estar llegando, así que se busca **esa** jornada por su
        id y se comprueba que el cierre cae dentro de la ventana.
        """
        activa = await WorkSessionsDAO.find_active_for_user(
            company_id=company_id, user_id=user_id
        )
        if activa is not None:
            return activa

        if event_kind is not LocationEventKind.END_WORK:
            # Sin jornada abierta no hay captura normal. §13: la captura sólo
            # está permitida mientras la jornada está ACTIVE.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Location evidence requires an active work session.",
            )

        cerrada = await WorkSessionsDAO.get_for_company_and_owner(
            session_id=subject_id, company_id=company_id, user_id=user_id
        )
        if cerrada is None or cerrada.status != WorkSessionStatus.ENDED.value:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_NO_ENCONTRADO
            )

        ventana = timedelta(
            seconds=int(_politica()["recovery_window_seconds"])
            + int(_politica()["sweeper_grace_seconds"])
        )
        if cerrada.ended_at is None or _ahora() - cerrada.ended_at > ventana:
            # La recuperación de End Work es **acotada** (§13). Pasada la
            # ventana, esa jornada ya no acepta nada: aceptarlo sería una vía
            # para escribir ubicación en jornadas antiguas.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The End Work recovery window for that session has closed.",
            )
        return cerrada

    @classmethod
    async def record(
        cls,
        *,
        company_id: int,
        user_id: int,
        payload: LocationEvidenceIn,
        received_at: datetime,
    ) -> tuple[LocationFix, bool]:
        """Registra un punto. Devuelve `(fila, era_reenvio)`."""
        jornada = await cls._jornada_autoritativa(
            company_id=company_id,
            user_id=user_id,
            event_kind=payload.event_kind,
            subject_id=payload.subject_id,
        )
        sujeto = await SubjectsDAO.resolve(
            company_id=company_id,
            event_kind=payload.event_kind,
            subject_id=payload.subject_id,
            work_session_id=jornada.id,
        )
        if sujeto is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_NO_ENCONTRADO
            )

        cls._validar_hora_de_captura(
            device_captured_at=payload.device_captured_at, received_at=received_at
        )
        cls._validar_calidad(payload)

        ya = await LocationFixesDAO.find_for_event(
            company_id=company_id,
            event_kind=payload.event_kind,
            subject_id=payload.subject_id,
        )
        if ya is not None:
            # Reenvío de la cola. No se sobrescribe: el primer punto es el que
            # se midió más cerca del evento, y §32 dice que evidencia cacheada
            # no pasa a fresca porque la subida ocurriera después.
            return ya, True

        fila = LocationFix(
            company_id=company_id,
            work_session_id=jornada.id,
            event_kind=payload.event_kind.value,
            subject_kind=sujeto.subject_kind.value,
            subject_id=sujeto.subject_id,
            evidence_level=payload.evidence_level.value,
            latitude=payload.latitude,
            longitude=payload.longitude,
            accuracy_m=payload.accuracy_m,
            device_captured_at=payload.device_captured_at,
            server_received_at=received_at,
            source_age_seconds=payload.source_age_seconds,
            permission_state=(
                payload.permission_state.value if payload.permission_state else None
            ),
        )
        try:
            async with transaction() as sesion:
                sesion.add(fila)
                await sesion.flush()
                nuevo_id = fila.id
        except IntegrityError:
            # Dos envíos a la vez del mismo punto. El índice único decide, y el
            # segundo lee el que ganó en vez de recibir un conflicto por algo
            # que hizo bien.
            existente = await LocationFixesDAO.find_for_event(
                company_id=company_id,
                event_kind=payload.event_kind,
                subject_id=payload.subject_id,
            )
            if existente is None:
                raise
            return existente, True

        await record_event(
            company_id=company_id,
            entity_type="location_fix",
            entity_id=nuevo_id,
            action="create",
            actor_user_id=user_id,
            summary=f"Location evidence for {payload.event_kind.value}",
            # Sin coordenadas en la traza (§35): lo que hace falta auditar es
            # que existe evidencia, de qué calidad y de qué evento.
            changes={
                "event_kind": payload.event_kind.value,
                "subject_id": sujeto.subject_id,
                "evidence_level": payload.evidence_level.value,
                "device_captured_at": payload.device_captured_at.isoformat(),
            },
        )
        return fila, False

    @staticmethod
    def _validar_hora_de_captura(
        *, device_captured_at: datetime, received_at: datetime
    ) -> None:
        """Descarta horas de captura imposibles sin confiar en el cliente.

        Dos hechos que el servidor sí conoce: una medición no puede ocurrir
        **después** de recibirse, y no puede ser arbitrariamente antigua. Es la
        misma comprobación de causalidad que `_resolve_occurrence` aplica a las
        acciones de jornada, aplicada aquí a la captura.
        """
        margen = timedelta(minutes=5)  # deriva de reloj razonable del dispositivo
        if device_captured_at > received_at + margen:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="device_captured_at cannot be in the future.",
            )
        if received_at - device_captured_at > timedelta(days=30):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="device_captured_at is implausibly old.",
            )

    @staticmethod
    def _validar_calidad(payload: LocationEvidenceIn) -> None:
        """Un punto cacheado tiene que cumplir los criterios configurados.

        §11: "cached evidence is eligible only if it meets configured
        freshness/accuracy criteria". El cliente ya lo comprueba, y volver a
        comprobarlo aquí no es desconfianza gratuita: el umbral es
        configuración del servidor y el cliente puede llevar una versión vieja.
        """
        if payload.evidence_level is not LocationEvidenceLevel.DEGRADED_CACHED:
            return
        politica = _politica()
        if (payload.source_age_seconds or 0) > int(politica["cached_max_age_seconds"]):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="That cached point is older than this company allows.",
            )
        limite = int(politica["cached_max_accuracy_m"])
        if payload.accuracy_m is not None and payload.accuracy_m > limite:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="That cached point is less accurate than this company allows.",
            )

    @classmethod
    async def finalize_missing(
        cls,
        *,
        company_id: int,
        user_id: int,
        payload: MissingLocationIn,
    ) -> tuple[MissingLocationEvent, bool]:
        """Da por perdida la ubicación de un evento. Devuelve `(fila, era_reenvio)`.

        Sólo si **no** hay ya un punto: un cliente que reintenta podría llamar a
        las dos cosas, y el punto manda. Un `missing` junto a un punto válido
        haría que el motor de kilometraje tuviera que decidir cuál cree.
        """
        jornada = await cls._jornada_autoritativa(
            company_id=company_id,
            user_id=user_id,
            event_kind=payload.event_kind,
            subject_id=payload.subject_id,
        )
        sujeto = await SubjectsDAO.resolve(
            company_id=company_id,
            event_kind=payload.event_kind,
            subject_id=payload.subject_id,
            work_session_id=jornada.id,
        )
        if sujeto is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_NO_ENCONTRADO
            )

        punto = await LocationFixesDAO.find_for_event(
            company_id=company_id,
            event_kind=payload.event_kind,
            subject_id=payload.subject_id,
        )
        if punto is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That lifecycle event already has location evidence.",
            )

        return await cls._escribir_missing(
            company_id=company_id,
            user_id=user_id,
            event_kind=payload.event_kind,
            sujeto=sujeto,
            reason=payload.reason_code,
            permission_state=(
                payload.permission_state.value if payload.permission_state else None
            ),
            attempts=[a.model_dump(mode="json") for a in payload.attempts],
            rejected=_candidato_rechazado(payload),
        )

    @staticmethod
    async def _escribir_missing(
        *,
        company_id: int,
        user_id: int | None,
        event_kind: LocationEventKind,
        sujeto,
        reason: MissingLocationReason,
        permission_state: str | None,
        attempts: list[dict],
        rejected: dict | None,
    ) -> tuple[MissingLocationEvent, bool]:
        ya = await MissingLocationEventsDAO.find_for_event(
            company_id=company_id, event_kind=event_kind, subject_id=sujeto.subject_id
        )
        if ya is not None:
            # G5 pide **exactamente un** evento. El reenvío devuelve el que hay.
            return ya, True

        fila = MissingLocationEvent(
            company_id=company_id,
            work_session_id=sujeto.work_session_id,
            trip_id=sujeto.trip_id,
            event_kind=event_kind.value,
            subject_kind=sujeto.subject_kind.value,
            subject_id=sujeto.subject_id,
            occurred_at=sujeto.occurred_at,
            reason_code=reason.value,
            attempts=attempts,
            permission_state=permission_state,
            rejected_candidate=rejected,
            notification_status=MissingNotificationStatus.PENDING.value,
        )
        try:
            async with transaction() as sesion:
                sesion.add(fila)
                await sesion.flush()
                nuevo_id = fila.id
        except IntegrityError:
            existente = await MissingLocationEventsDAO.find_for_event(
                company_id=company_id,
                event_kind=event_kind,
                subject_id=sujeto.subject_id,
            )
            if existente is None:
                raise
            return existente, True

        await record_event(
            company_id=company_id,
            entity_type="missing_location_event",
            entity_id=nuevo_id,
            action="create",
            actor_user_id=user_id,
            summary=f"Location missing for {event_kind.value}",
            changes={
                "event_kind": event_kind.value,
                "subject_id": sujeto.subject_id,
                "reason_code": reason.value,
                "occurred_at": sujeto.occurred_at.isoformat(),
            },
        )
        return fila, False


def _candidato_rechazado(payload: MissingLocationIn) -> dict | None:
    """Edad y precisión del punto que se descartó. Nunca su posición."""
    if payload.rejected_age_seconds is None and payload.rejected_accuracy_m is None:
        return None
    datos: dict = {}
    if payload.rejected_age_seconds is not None:
        datos["age_seconds"] = payload.rejected_age_seconds
    if payload.rejected_accuracy_m is not None:
        datos["accuracy_m"] = str(payload.rejected_accuracy_m)
    return datos


async def sweep_unreported_windows(*, limit: int = 200) -> int:
    """Cierra los eventos cuya ventana venció sin que el cliente volviera.

    Es el tercer camino de la recuperación, y sin él la evidencia se quedaría
    en un limbo: el cliente inicia la ventana, cierra el navegador, y nadie
    vuelve a hablar de ese evento nunca. Es la misma enfermedad que §24 prohíbe
    para `Pending`, sólo en otra tabla.

    Se hace en SQL sobre las tres clases de sujeto porque la pregunta es
    "eventos ocurridos hace más que la ventana, sin punto y sin missing", y
    resolverla en Python obligaría a traer los candidatos de cuatro tablas.

    `subject_kind_for` no se usa aquí: la consulta ya emite la pareja correcta
    por construcción, y el `CHECK` de la tabla la verifica al insertar.
    """
    politica = _politica()
    limite = timedelta(
        seconds=int(politica["recovery_window_seconds"])
        + int(politica["sweeper_grace_seconds"])
    )
    corte = _ahora() - limite

    from sqlalchemy import text as _text

    consulta = _text(
        """
        SELECT * FROM (
            SELECT t.company_id, t.work_session_id, t.id AS trip_id,
                   'start_trip' AS event_kind, 'trip' AS subject_kind,
                   t.id AS subject_id, t.started_at AS occurred_at
            FROM trip t WHERE t.started_at IS NOT NULL

            UNION ALL

            SELECT t.company_id, t.work_session_id, t.id,
                   'arrived', 'trip', t.id, t.arrived_at
            FROM trip t WHERE t.arrived_at IS NOT NULL

            UNION ALL

            SELECT c.company_id, t.work_session_id, c.trip_id,
                   'change_plan', 'trip_purpose_change', c.id, c.changed_at
            FROM trip_purpose_change c
            JOIN trip t ON t.id = c.trip_id AND t.company_id = c.company_id
        ) e
        WHERE e.occurred_at < :corte
          AND NOT EXISTS (
              SELECT 1 FROM location_fix f
              WHERE f.company_id = e.company_id
                AND f.event_kind = e.event_kind
                AND f.subject_id = e.subject_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM missing_location_event m
              WHERE m.company_id = e.company_id
                AND m.event_kind = e.event_kind
                AND m.subject_id = e.subject_id
          )
        ORDER BY e.occurred_at
        LIMIT :limite
        """
    )

    from app.core.db.session import db_session

    async with db_session() as sesion:
        candidatos = (
            await sesion.execute(consulta, {"corte": corte, "limite": limit})
        ).all()

    cerrados = 0
    for fila in candidatos:
        async with transaction() as sesion:
            sesion.add(
                MissingLocationEvent(
                    company_id=fila.company_id,
                    work_session_id=fila.work_session_id,
                    trip_id=fila.trip_id,
                    event_kind=fila.event_kind,
                    subject_kind=fila.subject_kind,
                    subject_id=fila.subject_id,
                    occurred_at=fila.occurred_at,
                    # El motivo es el hecho observable, no una suposición sobre
                    # el dispositivo: el cliente no volvió a decir nada (§29).
                    reason_code=MissingLocationReason.NO_CLIENT_REPORT.value,
                    attempts=[],
                    notification_status=MissingNotificationStatus.PENDING.value,
                )
            )
        cerrados += 1

    return cerrados
