"""
Reglas de la evidencia de odómetro.

Las cinco que sostienen el módulo:

1. **`Start Work` ≠ `Start Driving`.** Abrir la jornada no pide odómetro. Si hay
   vehículo, la lectura inicial queda `PENDING` y el supervisor puede trabajar
   en lo que no implique conducir.
2. **La guarda es del servidor.** `Start Trip` no sale si la lectura inicial
   sigue sin resolverse. Que la pantalla esconda el botón es experiencia de
   usuario, no un control.
3. **Foto + confirmación es la evidencia primaria.** El OCR sugiere; la persona
   confirma. Si el OCR no ve nada, el supervisor teclea lo que lee y **sigue
   siendo evidencia fotográfica normal**, sin aprobación de nadie.
4. **Teclear sin foto es excepcional.** Exige una solicitud con motivo,
   aprobación de un administrador, y vale **una sola vez** para esa jornada, ese
   vehículo y ese extremo.
5. **Nada se inventa.** Sin vehículo aplicable la lectura es `NOT_REQUIRED`, no
   un cero. Sin lectura de cierre no hay distancia, no una distancia cero.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.audit.service import record_event
from app.core.db.session import db_session, transaction
from app.routers_api.odometer.dao import (
    OdometerEvidenceDAO,
    OdometerExceptionRequestsDAO,
)
from app.routers_api.odometer.models import (
    END_WORK_UNBLOCKING_STATUSES,
    RESOLVED_STATUSES,
    OdometerEvidence,
    OdometerEvidenceMethod,
    OdometerEvidenceType,
    OdometerExceptionRequest,
    OdometerExceptionStatus,
    OdometerStatus,
)
from app.routers_api.odometer.ocr import get_odometer_reader
from app.routers_api.worksessions.models import WorkSession, WorkSessionStatus


class OdometerService:
    # ── Estado ──────────────────────────────────────────────────────────────

    @staticmethod
    async def ensure_row(
        *, company_id: int, work_session_id: int, evidence_type: str
    ) -> OdometerEvidence:
        """La fila de ese extremo, creándola en su estado inicial si falta.

        El estado inicial depende de si la jornada llevaba vehículo: con
        vehículo nace `PENDING`; sin él, `NOT_REQUIRED`. Decidirlo aquí y no en
        la pantalla es lo que hace que la guarda sea del servidor.
        """
        existente = await OdometerEvidenceDAO.find(
            company_id=company_id,
            work_session_id=work_session_id,
            evidence_type=evidence_type,
        )
        if existente is not None:
            return existente

        # El `try` envuelve **todo** el `async with`, no sólo el `flush`.
        # Capturarlo dentro dejaba la sesión con su transacción ya deshecha, y
        # entonces el `commit()` del gestor de contexto lanzaba
        # `PendingRollbackError`: un 500 en la cara del supervisor cada vez que
        # dos pestañas o dos dispositivos leían el estado a la vez, que es lo
        # normal y no un caso raro.
        try:
            async with transaction() as session:
                jornada = await session.scalar(
                    select(WorkSession).where(WorkSession.id == work_session_id)
                )
                vehicle_id = jornada.vehicle_id if jornada else None
                inicial = (
                    OdometerStatus.PENDING.value
                    if vehicle_id is not None
                    else OdometerStatus.NOT_REQUIRED.value
                )
                fila = OdometerEvidence(
                    company_id=company_id,
                    work_session_id=work_session_id,
                    vehicle_id=vehicle_id,
                    evidence_type=evidence_type,
                    status=inicial,
                )
                session.add(fila)
                await session.flush()
        except IntegrityError:
            # Otra petición la creó primero. El índice único hizo su trabajo y
            # aquí no hay nada que arreglar: se devuelve la fila que ya existe.
            pass

        return await OdometerEvidenceDAO.find(
            company_id=company_id,
            work_session_id=work_session_id,
            evidence_type=evidence_type,
        )

    @staticmethod
    async def ensure_start_reading_resolved(
        *, company_id: int, work_session_id: int
    ) -> None:
        """La guarda dura de `Start Trip`.

        Una excepción *aprobada* todavía no es una lectura: desbloquea teclear,
        no salir. Hasta que el supervisor confirme el valor, el viaje no
        arranca.
        """
        fila = await OdometerService.ensure_row(
            company_id=company_id,
            work_session_id=work_session_id,
            evidence_type=OdometerEvidenceType.START.value,
        )
        if fila.status in RESOLVED_STATUSES:
            return

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Capture the starting odometer reading before your first trip.",
        )

    @staticmethod
    async def ensure_end_work_not_blocked(
        *, company_id: int, work_session_id: int
    ) -> None:
        """La guarda de `End Work`, que es **más blanda** que la de `Start Trip`.

        Y lo es a propósito (Opción B de CER). Para salir a conducir hace falta
        una lectura confirmada. Para terminar el día basta con haber pedido la
        excepción: el supervisor ya no va a conducir más, y retenerle la jornada
        abierta hasta que alguien revise su solicitud acabaría escribiendo un
        `ended_at` que no ocurrió. La jornada se cierra a su hora real y la
        evidencia queda explícitamente pendiente.

        Lo que sí bloquea es `PENDING`: si la lectura de cierre hace falta y el
        supervisor no ha hecho ni la foto ni la solicitud, todavía hay algo que
        pedirle.
        """
        fila = await OdometerService.end_requirement(
            company_id=company_id, work_session_id=work_session_id
        )
        if fila.status in END_WORK_UNBLOCKING_STATUSES:
            return

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Capture the ending odometer reading before you end your day.",
        )

    # ── Camino normal: foto + confirmación ──────────────────────────────────

    @staticmethod
    async def attach_photo(
        *,
        company_id: int,
        work_session_id: int,
        evidence_type: str,
        image: bytes,
        content_type: str,
        original_filename: str | None,
        actor_user_id: int,
    ) -> tuple[OdometerEvidence, Decimal | None]:
        """Guarda la foto privada e intenta una sugerencia.

        La clave de almacenamiento **la genera el servidor**, nunca se deriva
        del nombre que envía quien sube el archivo. El contenido se valida y se
        escanea con las primitivas que ya existen.

        Devuelve la sugerencia del OCR aparte, para que la pantalla la enseñe
        como borrador. Que sea `None` es normal y no bloquea nada.
        """
        from app.core.storage.base import get_storage
        from app.core.storage.media import resolve_content_type
        from app.core.storage.scanning import ScanVerdict, get_scanner, scan_safely

        await OdometerService._negar_foto_tardia(
            company_id=company_id,
            work_session_id=work_session_id,
            evidence_type=evidence_type,
        )

        tipo = resolve_content_type(data=image, declared=content_type)
        if not tipo.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The odometer evidence must be a photo.",
            )

        # El análisis va **antes** de guardar, y su veredicto se guarda tal cual.
        #
        # Una foto que el escáner rechaza no se almacena: el supervisor hace otra.
        # Guardar una amenaza como "evidencia" no serviría a nadie, y aquí sí hay
        # un juicio sobre el archivo, no una avería.
        #
        # `not_configured` y `unavailable` son otra cosa: no dicen nada de la
        # foto, dicen que nadie pudo mirarla. Se guardan así, sin maquillar. Un
        # despliegue sin escáner es el caso por defecto y no puede quedarse sin
        # poder registrar su kilometraje; lo que no puede es que luego alguien
        # afirme que la foto se revisó.
        veredicto = scan_safely(get_scanner(), data=image, content_type=tipo)
        if veredicto.verdict == ScanVerdict.REJECTED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="That file was rejected by the malware scanner. Take a new photo.",
            )

        almacen = get_storage()
        objeto = almacen.put(
            data=image,
            content_type=tipo,
            original_filename=original_filename,
            scope=f"odometer/{company_id}",
        )

        sugerencia = get_odometer_reader().suggest(image=image, content_type=tipo)
        ahora = datetime.now(timezone.utc)

        await OdometerService.ensure_row(
            company_id=company_id,
            work_session_id=work_session_id,
            evidence_type=evidence_type,
        )

        async with transaction() as session:
            fila = await session.scalar(
                select(OdometerEvidence).where(
                    OdometerEvidence.company_id == company_id,
                    OdometerEvidence.work_session_id == work_session_id,
                    OdometerEvidence.evidence_type == evidence_type,
                )
            )
            fila.storage_key = objeto.storage_key
            fila.content_hash = objeto.content_hash
            fila.content_type = objeto.content_type
            fila.byte_size = objeto.byte_size
            fila.captured_at = ahora
            fila.scan_status = veredicto.verdict.value
            fila.scan_provider = veredicto.provider
            fila.scan_detail = veredicto.detail
            fila.ocr_detected_reading = sugerencia
            fila.version = fila.version + 1
            await session.flush()
            evidencia_id = fila.id

        await record_event(
            company_id=company_id,
            entity_type="odometer_evidence",
            entity_id=evidencia_id,
            action="photo_captured",
            actor_user_id=actor_user_id,
            summary=f"Odometer {evidence_type} photo captured",
            # Ni bytes ni nombre de fichero en la traza: la foto puede llevar
            # salpicadero y matrícula.
            changes={
                "evidence_type": {"old": None, "new": evidence_type},
                "ocr_suggested": {"old": None, "new": str(sugerencia) if sugerencia else None},
                # Queda por escrito si alguien miró el archivo y con qué
                # proveedor. Nadie podrá dar por revisada una foto que no lo fue.
                "scan_status": {"old": None, "new": veredicto.verdict.value},
                "scan_provider": {"old": None, "new": veredicto.provider},
            },
        )

        actualizada = await OdometerEvidenceDAO.find(
            company_id=company_id,
            work_session_id=work_session_id,
            evidence_type=evidence_type,
        )
        return actualizada, sugerencia

    @staticmethod
    async def _negar_foto_tardia(
        *, company_id: int, work_session_id: int, evidence_type: str
    ) -> None:
        """Una jornada cerrada ya no acepta una foto de cierre nueva.

        Es lo que mantiene el control en pie. La Opción B deja terminar el día
        con la excepción **pedida**, así que sin esta regla cualquiera podría
        cerrar la jornada, subir después una fotografía cualquiera y
        autoconfirmarla como `PHOTO_CONFIRMED`: la aprobación del administrador
        pasaría a ser decorativa y la vía manual, evitable.

        La Opción B ya dice cuál es el camino de cierre tardío —"el supervisor
        completa la lectura manual **de un solo uso**"—, y esta regla lo hace
        cumplir en vez de confiar en que nadie encuentre el atajo. El momento de
        la foto de cierre es cuando se cierra el día; pasado eso, una foto
        retrasada no es evidencia de la misma cosa.
        """
        if evidence_type != OdometerEvidenceType.END.value:
            return

        async with db_session() as session:
            jornada = await session.scalar(
                select(WorkSession).where(
                    WorkSession.id == work_session_id,
                    WorkSession.company_id == company_id,
                )
            )
        if jornada is None or jornada.status != WorkSessionStatus.ENDED.value:
            return

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Your workday is already closed. The ending reading can only be "
                "completed through the approved manual entry."
            ),
        )

    @staticmethod
    async def confirm_reading(
        *,
        company_id: int,
        work_session_id: int,
        evidence_type: str,
        reading: Decimal,
        actor_user_id: int,
    ) -> OdometerEvidence:
        """El supervisor confirma o corrige la lectura. Aquí está la autoridad.

        Con foto, el resultado es `PHOTO_CONFIRMED` aunque el OCR no hubiera
        sugerido nada: teclear lo que se ve en la foto es el camino normal.

        Sin foto sólo se llega aquí con una excepción **aprobada**, y entonces
        el resultado es `MANUAL_EXCEPTION_CONFIRMED`, que queda distinguible
        para siempre de la evidencia fotográfica.
        """
        fila = await OdometerService.ensure_row(
            company_id=company_id,
            work_session_id=work_session_id,
            evidence_type=evidence_type,
        )

        tiene_foto = fila.storage_key is not None
        aprobacion = None

        if not tiene_foto:
            aprobacion = await OdometerExceptionRequestsDAO.find_approved(
                company_id=company_id,
                work_session_id=work_session_id,
                evidence_type=evidence_type,
            )
            if aprobacion is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Add an odometer photo, or request approval to enter the "
                        "reading without one."
                    ),
                )

        if evidence_type == OdometerEvidenceType.END.value:
            await OdometerService._validar_contra_inicio(
                company_id=company_id,
                work_session_id=work_session_id,
                reading=reading,
            )

        ahora = datetime.now(timezone.utc)
        nuevo_estado = (
            OdometerStatus.PHOTO_CONFIRMED.value
            if tiene_foto
            else OdometerStatus.MANUAL_EXCEPTION_CONFIRMED.value
        )
        metodo = (
            OdometerEvidenceMethod.PHOTO.value
            if tiene_foto
            else OdometerEvidenceMethod.MANUAL_NO_PHOTO.value
        )

        async with transaction() as session:
            actual = await session.scalar(
                select(OdometerEvidence).where(OdometerEvidence.id == fila.id)
            )
            actual.confirmed_reading = reading
            actual.confirmed_at = ahora
            actual.confirmed_by = actor_user_id
            actual.status = nuevo_estado
            actual.evidence_method = metodo
            actual.version = actual.version + 1

            if aprobacion is not None:
                # Un solo uso: consumida, no vuelve a autorizar nada.
                consumida = await session.scalar(
                    select(OdometerExceptionRequest).where(
                        OdometerExceptionRequest.id == aprobacion.id
                    )
                )
                consumida.status = OdometerExceptionStatus.CONSUMED.value
                consumida.consumed_at = ahora
                consumida.version = consumida.version + 1

            await session.flush()

        await record_event(
            company_id=company_id,
            entity_type="odometer_evidence",
            entity_id=fila.id,
            action="reading_confirmed",
            actor_user_id=actor_user_id,
            summary=f"Odometer {evidence_type} reading confirmed",
            changes={
                "confirmed_reading": {"old": None, "new": str(reading)},
                "status": {"old": fila.status, "new": nuevo_estado},
                "evidence_method": {"old": None, "new": metodo},
            },
        )

        return await OdometerEvidenceDAO.find(
            company_id=company_id,
            work_session_id=work_session_id,
            evidence_type=evidence_type,
        )

    @staticmethod
    async def _validar_contra_inicio(
        *, company_id: int, work_session_id: int, reading: Decimal
    ) -> None:
        """Una lectura de cierre no puede ser menor que la de inicio.

        No se corrige en silencio ni se publica una distancia inventada: se
        rechaza y el supervisor vuelve a mirar el cuentakilómetros.
        """
        inicio = await OdometerEvidenceDAO.find(
            company_id=company_id,
            work_session_id=work_session_id,
            evidence_type=OdometerEvidenceType.START.value,
        )
        if inicio is None or inicio.confirmed_reading is None:
            return
        if reading < inicio.confirmed_reading:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "The ending reading cannot be lower than the starting one."
                ),
            )

    # ── Excepción sin foto ──────────────────────────────────────────────────

    @staticmethod
    async def request_exception(
        *,
        company_id: int,
        work_session_id: int,
        evidence_type: str,
        reason: str,
        reason_note: str | None,
        actor_user_id: int,
        auto_approve: bool = False,
    ) -> OdometerExceptionRequest:
        """Pide permiso para teclear sin foto, y con `auto_approve` se lo da.

        `auto_approve` es lo que el servidor averiguo del permiso real de quien
        llama (`route.odometer.selfapprove`), nunca algo que venga del cuerpo de
        la peticion. Por defecto es `False`, de modo que el flujo de siempre
        -pedir y esperar al administrador- es el que se obtiene si nadie
        concede nada.

        Lo que la autoaprobacion hace es **saltarse la espera**, no la
        excepcion: la solicitud queda `approved`, la evidencia pasa a
        `exception_approved`, y el supervisor sigue teniendo que teclear su
        lectura, que entrara como `manual_no_photo`. No se escribe ninguna
        lectura ni se fabrica ninguna foto.

        Es una medida temporal de estabilizacion. Retirar la capacidad del rol
        devuelve el comportamiento anterior sin tocar codigo.
        """
        fila = await OdometerService.ensure_row(
            company_id=company_id,
            work_session_id=work_session_id,
            evidence_type=evidence_type,
        )
        if fila.status in RESOLVED_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This odometer reading is already resolved.",
            )

        ahora = datetime.now(timezone.utc)

        try:
            async with transaction() as session:
                solicitud = OdometerExceptionRequest(
                    company_id=company_id,
                    work_session_id=work_session_id,
                    vehicle_id=fila.vehicle_id,
                    evidence_type=evidence_type,
                    reason=reason,
                    reason_note=reason_note,
                    requested_by=actor_user_id,
                    requested_at=ahora,
                )
                session.add(solicitud)
                await session.flush()
                solicitud_id = solicitud.id

                evidencia = await session.scalar(
                    select(OdometerEvidence).where(OdometerEvidence.id == fila.id)
                )
                if auto_approve:
                    # En la **misma** transaccion: si se partiera en dos, entre
                    # una y otra existiria una solicitud pedida y sin decidir
                    # que un administrador podria ver y decidir, y acabariamos
                    # con dos decisiones sobre el mismo hecho.
                    #
                    # `decided_by` queda en NULL a proposito: no hubo persona.
                    # Poner al propio supervisor diria que se aprobo a si mismo,
                    # y poner a un administrador seria inventarlo. La columna ya
                    # era nulable, y "decidida sin decisor" es exactamente lo
                    # que paso.
                    solicitud.status = OdometerExceptionStatus.APPROVED.value
                    solicitud.decided_at = ahora
                    evidencia.status = OdometerStatus.EXCEPTION_APPROVED.value
                else:
                    evidencia.status = OdometerStatus.EXCEPTION_REQUESTED.value
                evidencia.version = evidencia.version + 1
                await session.flush()
        except IntegrityError:
            # El índice parcial impide dos solicitudes vivas para el mismo
            # extremo: pedirla dos veces no abre dos puertas.
            viva = await OdometerExceptionRequestsDAO.find_open(
                company_id=company_id,
                work_session_id=work_session_id,
                evidence_type=evidence_type,
            )
            if viva is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not submit the request. Try again.",
                )
            return viva

        await record_event(
            company_id=company_id,
            entity_type="odometer_exception_request",
            entity_id=solicitud_id,
            action="request",
            actor_user_id=actor_user_id,
            summary=f"Manual odometer entry requested for {evidence_type}",
            changes={"reason": {"old": None, "new": reason}},
        )

        if auto_approve:
            # Un evento aparte, y con accion propia. Dos eventos cuentan los dos
            # hechos: se pidio, y se aprobo sola. Reutilizar `approve` la haria
            # indistinguible de la decision de una persona en cuanto alguien
            # leyera la auditoria, que es lo contrario de lo que se pide.
            await record_event(
                company_id=company_id,
                entity_type="odometer_exception_request",
                entity_id=solicitud_id,
                action="auto_approve",
                actor_user_id=actor_user_id,
                summary=(
                    f"Manual odometer entry auto-approved for {evidence_type} "
                    "under route.odometer.selfapprove"
                ),
                changes={
                    "status": {"old": "requested", "new": "approved"},
                    "decided_by": {"old": None, "new": None},
                },
            )

        return await OdometerExceptionRequestsDAO.get_for_company(
            request_id=solicitud_id, company_id=company_id
        )

    @staticmethod
    async def decide_exception(
        *,
        company_id: int,
        request_id: int,
        approve: bool,
        actor_user_id: int,
    ) -> OdometerExceptionRequest:
        """El administrador aprueba o rechaza. Autoridad distinta de la del campo.

        Aprobar **no** escribe ninguna lectura: sólo abre la puerta para que el
        supervisor teclee la suya. Rechazar devuelve la evidencia a `PENDING`,
        y el viaje sigue bloqueado hasta que haya evidencia válida.
        """
        solicitud = await OdometerExceptionRequestsDAO.get_for_company(
            request_id=request_id, company_id=company_id
        )
        if solicitud is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Request not found",
            )
        if solicitud.status != OdometerExceptionStatus.REQUESTED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This request has already been decided.",
            )

        ahora = datetime.now(timezone.utc)
        nuevo = (
            OdometerExceptionStatus.APPROVED.value
            if approve
            else OdometerExceptionStatus.REJECTED.value
        )

        async with transaction() as session:
            # La comprobación de arriba no basta: dos administradores mirando la
            # misma cola es lo normal, y entre leer el estado y escribirlo cabe
            # la decisión del otro. Sin esta condición en el `UPDATE`, los dos
            # recibían 200 y la auditoría se quedaba con una aprobación **y** un
            # rechazo de la misma solicitud, mientras el estado final era el del
            # último en escribir. Ahora la base decide quién llegó primero.
            aplicado = await session.execute(
                update(OdometerExceptionRequest)
                .where(
                    OdometerExceptionRequest.id == request_id,
                    OdometerExceptionRequest.company_id == company_id,
                    OdometerExceptionRequest.status
                    == OdometerExceptionStatus.REQUESTED.value,
                )
                .values(
                    status=nuevo,
                    decided_by=actor_user_id,
                    decided_at=ahora,
                    version=OdometerExceptionRequest.version + 1,
                )
            )
            if aplicado.rowcount == 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This request has already been decided.",
                )

            evidencia = await session.scalar(
                select(OdometerEvidence).where(
                    OdometerEvidence.company_id == company_id,
                    OdometerEvidence.work_session_id == solicitud.work_session_id,
                    OdometerEvidence.evidence_type == solicitud.evidence_type,
                )
            )
            if evidencia is not None:
                evidencia.status = (
                    OdometerStatus.EXCEPTION_APPROVED.value
                    if approve
                    else OdometerStatus.PENDING.value
                )
                evidencia.version = evidencia.version + 1
            await session.flush()

        await record_event(
            company_id=company_id,
            entity_type="odometer_exception_request",
            entity_id=request_id,
            action="approve" if approve else "reject",
            actor_user_id=actor_user_id,
            summary=(
                "Manual odometer entry approved"
                if approve
                else "Manual odometer entry rejected; photo required"
            ),
            changes={"status": {"old": solicitud.status, "new": nuevo}},
        )

        return await OdometerExceptionRequestsDAO.get_for_company(
            request_id=request_id, company_id=company_id
        )

    # ── Distancia derivada ──────────────────────────────────────────────────

    @staticmethod
    def _distance(
        inicio: OdometerEvidence | None, fin: OdometerEvidence | None
    ) -> Decimal | None:
        """`fin - inicio`, o `None` si falta alguna de las dos.

        **No es millaje de ruta** y nunca lo alimenta. `None` significa que
        todavía no se puede afirmar una distancia: no es cero.

        Recibe las filas en vez de buscarlas porque quien la llama ya las tiene:
        ver `session_state`.
        """
        if (
            inicio is None
            or fin is None
            or inicio.confirmed_reading is None
            or fin.confirmed_reading is None
        ):
            return None
        return fin.confirmed_reading - inicio.confirmed_reading

    @staticmethod
    async def session_state(
        *, company_id: int, work_session_id: int
    ) -> tuple[OdometerEvidence, OdometerEvidence | None, Decimal | None]:
        """Los dos extremos y su distancia, leyendo cada fila **una vez**.

        Antes esto eran cinco consultas: la de inicio, la de fin, y otras dos
        para volver a buscar las mismas filas dentro del cálculo de distancia.
        La pantalla del supervisor lo llama en cada reconciliación, así que la
        diferencia no es teórica — y en los tests, donde cada consulta abre su
        propia conexión física, la repetición llegó a agotar el servidor.
        """
        inicio = await OdometerService.ensure_row(
            company_id=company_id,
            work_session_id=work_session_id,
            evidence_type=OdometerEvidenceType.START.value,
        )
        fin = await OdometerEvidenceDAO.find(
            company_id=company_id,
            work_session_id=work_session_id,
            evidence_type=OdometerEvidenceType.END.value,
        )
        return inicio, fin, OdometerService._distance(inicio, fin)

    @staticmethod
    async def end_requirement(
        *, company_id: int, work_session_id: int
    ) -> OdometerEvidence:
        """El estado de la lectura de cierre cuando el supervisor va a terminar.

        Sólo se exige si la jornada llegó a usar su vehículo: sin ningún viaje
        arrancado no hay distancia que cerrar, y pedir una foto sería inventar
        una necesidad.
        """
        from app.routers_api.trips.dao import TripsDAO

        fila = await OdometerService.ensure_row(
            company_id=company_id,
            work_session_id=work_session_id,
            evidence_type=OdometerEvidenceType.END.value,
        )
        if fila.status != OdometerStatus.PENDING.value:
            return fila

        condujo = await TripsDAO.count_vehicle_trips(
            company_id=company_id, work_session_id=work_session_id
        )
        if condujo and fila.vehicle_id is not None:
            return fila

        async with transaction() as session:
            actual = await session.scalar(
                select(OdometerEvidence).where(OdometerEvidence.id == fila.id)
            )
            actual.status = OdometerStatus.NOT_REQUIRED.value
            actual.version = actual.version + 1
            await session.flush()

        return await OdometerEvidenceDAO.find(
            company_id=company_id,
            work_session_id=work_session_id,
            evidence_type=OdometerEvidenceType.END.value,
        )
