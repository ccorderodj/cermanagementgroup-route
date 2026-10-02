"""La excepción de odómetro se autoaprueba, si el rol tiene la capacidad.

Qué es esto y qué no
--------------------
Medida **temporal** de estabilización autorizada por CER: que el día del
supervisor no se detenga esperando a que un administrador apruebe su excepción
de odómetro. Lo único que la capacidad `route.odometer.selfapprove` quita es la
espera.

Lo que no cambia, y estos tests lo comprueban: la excepción sigue siendo una
excepción, con su motivo cerrado y toda su trazabilidad; la lectura sigue
entrando como `manual_no_photo`; no se fabrica foto ni lectura; y quien no tiene
la capacidad conserva exactamente el flujo anterior.

Por qué la reversión está probada
---------------------------------
Porque es la garantía que hace aceptable la medida. Si retirar la capacidad no
devolviera el flujo manual, esto no sería temporal: sería un cambio permanente
con un interruptor que no apaga. El último test lo ejercita.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.database import async_session_maker
from tests.integration.test_odometer import _jornada_con_vehiculo


pytestmark = pytest.mark.integration


CAPACIDAD = "route.odometer.selfapprove"


async def _conceder(seeded, rol: str = "supervisor") -> None:
    """Concede la capacidad al rol, como lo haría la pantalla de permisos."""
    async with async_session_maker() as sesion:
        await sesion.execute(
            text(
                "INSERT INTO role_permission (role_id, permission_id, is_active) "
                "SELECT :r, p.id, true FROM permission p WHERE p.name = :c"
            ),
            {"r": seeded.alpha.roles[rol], "c": CAPACIDAD},
        )
        await sesion.commit()


async def _retirar(seeded, rol: str = "supervisor") -> None:
    """La reversión: se quita la concesión y nada más."""
    async with async_session_maker() as sesion:
        await sesion.execute(
            text(
                "DELETE FROM role_permission rp USING permission p "
                "WHERE rp.permission_id = p.id AND rp.role_id = :r AND p.name = :c"
            ),
            {"r": seeded.alpha.roles[rol], "c": CAPACIDAD},
        )
        await sesion.commit()


async def _solicitud(seeded, session_id: int, tipo: str) -> dict:
    async with async_session_maker() as sesion:
        fila = (
            await sesion.execute(
                text(
                    "SELECT status, decided_by, decided_at, requested_by, reason "
                    "FROM odometer_exception_request "
                    "WHERE company_id = :c AND work_session_id = :s "
                    "AND evidence_type = :t"
                ),
                {"c": seeded.alpha.id, "s": session_id, "t": tipo},
            )
        ).first()
    return dict(fila._mapping) if fila else {}


async def _auditoria(seeded, entity_id: int) -> list[dict]:
    async with async_session_maker() as sesion:
        filas = await sesion.execute(
            text(
                "SELECT action, actor_user_id, summary FROM audit_event "
                "WHERE company_id = :c AND entity_type = 'odometer_exception_request' "
                "AND entity_id = :e ORDER BY id"
            ),
            {"c": seeded.alpha.id, "e": entity_id},
        )
        return [dict(f._mapping) for f in filas]


@pytest.mark.parametrize("tipo", ["start", "end"])
async def test_con_la_capacidad_la_excepcion_se_autoaprueba(
    seeded, alpha_client, tipo
):
    """Con la capacidad, pedirla es obtenerla. En los dos extremos.

    `end` se prueba igual que `start` porque el estancamiento ocurre en los dos
    y CER autorizó ambos: la jornada se queda esperando lo mismo al terminar.
    """
    await _conceder(seeded)
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    respuesta = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/{tipo}/exception",
        json={"reason": "camera_unavailable", "reason_note": None},
    )

    assert respuesta.status_code in (200, 201), respuesta.text
    assert respuesta.json()["status"] == "approved", respuesta.json()

    fila = await _solicitud(seeded, jornada["id"], tipo)
    assert fila["status"] == "approved", fila
    assert fila["decided_at"] is not None, "una decisión tiene su hora"
    assert fila["decided_by"] is None, (
        "no hubo persona: poner al supervisor diría que se aprobó a sí mismo y "
        "poner a un administrador sería inventarlo"
    )
    # Y sigue siendo una excepción con su motivo y su solicitante.
    assert fila["reason"] == "camera_unavailable", fila
    assert fila["requested_by"] == seeded.alpha.users["supervisor"].id, fila


async def test_sin_la_capacidad_sigue_esperando_al_administrador(
    seeded, alpha_client
):
    """Sin la capacidad, el flujo es exactamente el de antes.

    Es la mitad que hace acotada a la medida: instalar el código no cambia el
    comportamiento de nadie hasta que alguien concede la capacidad.
    """
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    respuesta = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/exception",
        json={"reason": "camera_unavailable", "reason_note": None},
    )

    assert respuesta.status_code in (200, 201), respuesta.text
    assert respuesta.json()["status"] == "requested", respuesta.json()

    fila = await _solicitud(seeded, jornada["id"], "start")
    assert fila["status"] == "requested", fila
    assert fila["decided_at"] is None, fila

    # Y teclear sin que un administrador haya aprobado sigue sin ser posible.
    manual = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "90210.0"},
    )
    assert manual.status_code == 409, manual.text


async def test_la_auditoria_distingue_la_automatica_de_la_humana(
    seeded, alpha_client
):
    """Quien lea la auditoría tiene que poder saber si decidió una persona.

    Dos eventos cuentan los dos hechos: se pidió, y se aprobó sola. Reutilizar
    la acción `approve` la haría indistinguible de la decisión de un
    administrador, que es justo lo que CER condicionó al aceptar
    `decided_by = NULL`.
    """
    await _conceder(seeded)
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    solicitud = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/exception",
            json={"reason": "permission_problem", "reason_note": None},
        )
    ).json()

    eventos = await _auditoria(seeded, solicitud["id"])
    acciones = [e["action"] for e in eventos]
    assert acciones == ["request", "auto_approve"], eventos
    automatico = eventos[1]
    assert CAPACIDAD in automatico["summary"], (
        "la traza dice bajo qué autorización se aprobó sola"
    )
    # El actor del evento es quien la pidió —es quien actuó— y el hecho de que
    # fuera automática lo dice la acción, no un actor inventado.
    assert automatico["actor_user_id"] == seeded.alpha.users["supervisor"].id


async def test_la_lectura_sigue_entrando_como_manual_sin_foto(
    seeded, alpha_client
):
    """Autoaprobar no fabrica nada: el supervisor sigue teniendo que teclear.

    Y lo que teclea queda marcado como lectura sin foto para siempre, que es lo
    que impide que una excepción se confunda después con evidencia fotográfica.
    """
    await _conceder(seeded)
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/exception",
        json={"reason": "no_usable_photo", "reason_note": "Glare on the dash"},
    )

    # Antes de teclear no hay lectura ni foto: aprobar abre la puerta, no la
    # cruza.
    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert estado["start"]["status"] == "exception_approved", estado
    assert estado["start"]["confirmed_reading"] is None, estado
    assert estado["start"]["captured_at"] is None, (
        "no se fabrica una foto que nadie tomó"
    )

    confirmada = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/confirm",
            json={"reading": "90210.0"},
        )
    ).json()

    assert confirmada["status"] == "manual_exception_confirmed", confirmada
    assert confirmada["evidence_method"] == "manual_no_photo", (
        "una lectura sin foto no puede parecer evidencia fotográfica"
    )


async def test_retirar_la_capacidad_restaura_el_flujo_anterior(
    seeded, alpha_client
):
    """La reversión, ejercitada: se quita la concesión y vuelve la espera.

    Es la garantía que hace aceptable la medida. Se concede, se comprueba que
    autoaprueba, se retira, y la siguiente excepción vuelve a quedarse en
    `requested` — sin tocar ninguna línea de código ni ningún despliegue.
    """
    await _conceder(seeded)
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    primera = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/exception",
            json={"reason": "camera_unavailable", "reason_note": None},
        )
    ).json()
    assert primera["status"] == "approved", primera

    await _retirar(seeded)

    # El otro extremo de la misma jornada, ya sin la capacidad.
    segunda = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/end/exception",
            json={"reason": "camera_unavailable", "reason_note": None},
        )
    ).json()

    assert segunda["status"] == "requested", (
        f"retirada la capacidad, la excepción vuelve a esperar: {segunda}"
    )
    fila = await _solicitud(seeded, jornada["id"], "end")
    assert fila["decided_at"] is None, fila
