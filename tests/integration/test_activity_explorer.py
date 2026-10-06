"""Activity Explorer: lo que la pantalla afirma del pasado tiene que ser cierto.

Qué defiende este archivo
--------------------------
El explorador no escribe nada, así que el riesgo no es corromper datos: es
**contar mal la historia**. Un panel que agrupa una parada de la 1:00 AM en el
día siguiente, o que parte un bloque de actividad en tres porque se
seleccionaron tres actividades, no rompe nada y se cree durante meses.

Por eso los tests se agrupan por la afirmación que hace la pantalla —este año
tuvo estos meses, esta semana estos días, esta parada duró esto— y cada uno
pone al dominio en un estado concreto por el camino real del producto.

La semana empieza el lunes, y sale de la línea base
----------------------------------------------------
No es una elección de implementación: los grupos de mes de V0.7 rompen en
`Sep 1–6`, `Sep 7–13`, `Sep 14–20` y `Sep 21–27`, y el 7, el 14 y el 21 de
septiembre de 2026 son lunes. Un test lo fija para que nadie lo cambie a
domingo por costumbre.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.database import async_session_maker
from app.routers_api.standardvalues.provisioning import provision_standard_values

pytestmark = pytest.mark.integration

RUTA = "/api/activity-explorer"

#: Un PNG de 1x1. La evidencia de odómetro no es lo que se prueba aquí.
FOTO = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


async def _perfil_y_vehiculo(
    alpha_client, seeded, *, unidad: str, usuario="supervisor", compania="alpha"
):
    """Supervisor con perfil y vehículo asignado, por API.

    `compania` existe para el test de aislamiento: el otro tenant se prepara
    con **su** administrador, porque entrar con el de alpha en el cliente de
    beta no es el estado que se quiere comprobar.
    """
    empresa = getattr(seeded, compania)
    await alpha_client.login(empresa.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": empresa.users[usuario].id}
        )
    ).json()
    assert "id" in perfil, perfil
    vehiculo = (
        await alpha_client.post(
            "/api/vehicles",
            json={
                "make": "Toyota", "model": "Hilux", "year": 2024, "unit": unidad,
                "fuel_grade": "regular", "operational_mpg": "24.00",
            },
        )
    ).json()
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )
    return perfil, vehiculo


async def _valores(cliente, company_id: int, lista: str) -> list[dict]:
    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=company_id)
        await session.commit()
    respuesta = await cliente.get(f"/api/standard-values/{lista}")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _jornada_con_parada(
    alpha_client, seeded, *, usuario="supervisor", proposito="client_visit",
    referencia="ABC Manufacturing", actividades=1, terminar=True, notas=None,
    cerrar_jornada=True,
) -> dict:
    """Una jornada con un viaje y su bloque de actividad, por el producto.

    Pasa por las guardas reales: odómetro de inicio resuelto, viaje planificado
    con su valor de contexto, salida, llegada y bloque. Un test que las saltara
    comprobaría un estado que el producto no puede alcanzar.
    """
    await alpha_client.login(seeded.alpha.users[usuario].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "100000.0"},
    )

    # Los dos conjuntos del dominio son disjuntos: `PRETRIP_STANDARD_LIST`
    # —Employee Visit, Check Delivery, Office— lleva valor al planificar, y
    # `POSTARRIVAL_ACTIVITY_LIST` —Client Visit, Recruiting, Other— lo lleva al
    # llegar. Un contexto que no está en el primero **no acepta** valor previo.
    plan: dict = {"purpose": proposito, "context_reference": referencia}
    if proposito in ("office", "employee_visit", "check_delivery"):
        lista = {"office": "office_purposes",
                 "employee_visit": "employee_visit_reasons",
                 "check_delivery": "delivery_types"}[proposito]
        plan["standard_value_id"] = (
            await _valores(alpha_client, seeded.alpha.id, lista)
        )[0]["id"]

    viaje = (await alpha_client.post("/api/trips", json=plan)).json()
    assert "id" in viaje, viaje
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    ids: list[int] = []
    if proposito == "client_visit":
        disponibles = await _valores(
            alpha_client, seeded.alpha.id, "client_visit_activities"
        )
        ids = [v["id"] for v in disponibles[:actividades]]

    inicio = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start", json={"activity_ids": ids}
    )
    assert inicio.status_code in (200, 201), inicio.text

    if terminar:
        resultados = await _valores(alpha_client, seeded.alpha.id, "outcomes")
        cuerpo = {"action": "complete", "outcome_id": resultados[0]["id"]}
        if notas is not None:
            cuerpo["notes"] = notas
        fin = await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/complete", json=cuerpo
        )
        assert fin.status_code == 200, fin.text

    if cerrar_jornada:
        # Hay que cerrarla: un supervisor no tiene dos jornadas abiertas, así
        # que sin esto la segunda llamada devolvería la misma y los días del
        # test se pisarían. El cierre pasa por su propia guarda de odómetro.
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/end/photo",
            files={"photo": ("odo.png", FOTO, "image/png")},
        )
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/end/confirm",
            json={"reading": "100120.0"},
        )
        cierre = await alpha_client.post(
            f"/api/worksessions/{jornada['id']}/end", json={}
        )
        assert cierre.status_code == 200, cierre.text

    return {"jornada": jornada, "viaje": viaje, "actividades": ids}


async def _fechar_jornada(jornada_id: int, dia: date) -> None:
    """Mueve el día de negocio de una jornada ya creada.

    El `session_date` se calcula al abrir y no se puede pedir por API: para
    probar años, meses y semanas distintos hace falta colocar jornadas en el
    pasado. Se hace aquí, en la preparación del test, y no tocando ninguna
    regla del producto: lo que se comprueba después es que el explorador
    **agrupa por ese campo**, que es justo lo que PR-02 exige.
    """
    async with async_session_maker() as session:
        await session.execute(
            text("UPDATE work_session SET session_date = :d WHERE id = :i"),
            {"d": dia, "i": jornada_id},
        )
        await session.commit()


async def _explorar(cliente, **parametros) -> dict:
    respuesta = await cliente.get(RUTA, params=parametros)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


# ── Autorización y aislamiento ──────────────────────────────────────────────


async def test_sin_la_capacidad_no_se_explora(seeded, alpha_client):
    """Un supervisor no lee la historia de los demás por adivinar la URL.

    Es la comprobación que §9 pide de forma explícita. El filtrado del frontend
    no es una frontera de autorización: la puerta está aquí.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    respuesta = await alpha_client.get(RUTA, params={"range": "day"})
    assert respuesta.status_code == 403, respuesta.text


async def test_el_administrador_de_route_si_explora(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    assert (await alpha_client.get(RUTA, params={"range": "day"})).status_code == 200


async def test_no_se_ve_el_supervisor_de_otro_tenant(
    seeded, alpha_client, beta_client
):
    """Y pedirlo por identificador devuelve 404, no 403.

    Un 403 confirmaría que ese supervisor existe en alguna parte. El 404 no
    dice nada, que es la regla de la casa para un recurso de otra compañía.
    """
    await _perfil_y_vehiculo(
        beta_client, seeded, unidad="V-BETA-EXP", compania="beta"
    )
    ajeno = seeded.beta.users["supervisor"].id

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.get(
        RUTA, params={"range": "day", "supervisor_user_id": ajeno}
    )
    assert respuesta.status_code == 404, respuesta.text


async def test_las_opciones_del_selector_son_del_tenant(seeded, alpha_client):
    """El selector de supervisor de la línea base, autorizado en el servidor."""
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-EXP-SEL")
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    cuerpo = await _explorar(alpha_client, range="day")

    ids = {s["user_id"] for s in cuerpo["supervisors"]}
    assert seeded.alpha.users["supervisor"].id in ids
    assert seeded.beta.users["supervisor"].id not in ids
    assert cuerpo["supervisor_user_id"] in ids, "queda uno seleccionado, como V0.7"


# ── La jerarquía ────────────────────────────────────────────────────────────


async def test_el_ano_agrupa_por_mes_y_solo_los_que_tienen_registros(
    seeded, alpha_client
):
    """FR-02 y FR-03: el año enseña sus meses, y no fabrica los vacíos.

    La línea base sólo dibuja los grupos que existen —sus días van de lunes a
    viernes porque el fin de semana no tuvo jornada—, así que doce filas de
    ceros serían una invención.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-EXP-ANO")
    primero = await _jornada_con_parada(alpha_client, seeded)
    await _fechar_jornada(primero["jornada"]["id"], date(2026, 3, 11))
    segundo = await _jornada_con_parada(alpha_client, seeded)
    await _fechar_jornada(segundo["jornada"]["id"], date(2026, 7, 22))

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _explorar(
        alpha_client, range="year", date="2026-07-22",
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )

    assert cuerpo["grouped_by"] == "month"
    assert cuerpo["start"] == "2026-01-01" and cuerpo["end"] == "2026-12-31"
    inicios = [g["start"] for g in cuerpo["groups"]]
    assert inicios == ["2026-03-01", "2026-07-01"], (
        f"se esperaban marzo y julio y nada más, salió {inicios}"
    )
    assert [g["activities"] for g in cuerpo["groups"]] == [1, 1]
    assert cuerpo["groups"][0]["drill_date"] == "2026-03-01", (
        "el botón de bajar nivel ancla en el primer día del grupo"
    )


async def test_el_mes_agrupa_por_semanas_de_lunes_a_domingo_recortadas(
    seeded, alpha_client
):
    """FR-04: la convención de semana de la línea base, fijada.

    Sus grupos de septiembre de 2026 son `Sep 1–6`, `Sep 7–13`, `Sep 14–20` y
    `Sep 21–27`; el 7, el 14 y el 21 son lunes. La primera semana se **recorta**
    al día 1 en vez de empezar en agosto, que es lo que produce ese grupo de
    seis días.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-EXP-MES")
    # Un día en la semana recortada y otro en una completa.
    uno = await _jornada_con_parada(alpha_client, seeded)
    await _fechar_jornada(uno["jornada"]["id"], date(2026, 9, 2))
    dos = await _jornada_con_parada(alpha_client, seeded)
    await _fechar_jornada(dos["jornada"]["id"], date(2026, 9, 16))

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _explorar(
        alpha_client, range="month", date="2026-09-16",
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )

    assert cuerpo["grouped_by"] == "week"
    rangos = [(g["start"], g["end"]) for g in cuerpo["groups"]]
    assert rangos == [("2026-09-01", "2026-09-06"), ("2026-09-14", "2026-09-20")], (
        f"la semana no es lunes-domingo recortada al mes: {rangos}"
    )


async def test_la_semana_agrupa_por_dias(seeded, alpha_client):
    """FR-05: la semana enseña sus días de negocio."""
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-EXP-SEM")
    lunes = await _jornada_con_parada(alpha_client, seeded)
    await _fechar_jornada(lunes["jornada"]["id"], date(2026, 9, 14))
    jueves = await _jornada_con_parada(alpha_client, seeded)
    await _fechar_jornada(jueves["jornada"]["id"], date(2026, 9, 17))

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _explorar(
        alpha_client, range="week", date="2026-09-17",
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )

    assert cuerpo["grouped_by"] == "day"
    assert cuerpo["start"] == "2026-09-14" and cuerpo["end"] == "2026-09-20"
    assert [g["start"] for g in cuerpo["groups"]] == ["2026-09-14", "2026-09-17"]
    assert all(g["start"] == g["end"] for g in cuerpo["groups"])


async def test_el_dia_enseña_las_paradas_y_no_agrupa(seeded, alpha_client):
    """FR-06: la hoja de la jerarquía son las paradas registradas."""
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-EXP-DIA")
    hecho = await _jornada_con_parada(
        alpha_client, seeded, referencia="ABC Manufacturing", notas="Pidió 4 más"
    )
    await _fechar_jornada(hecho["jornada"]["id"], date(2026, 9, 18))

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _explorar(
        alpha_client, range="day", date="2026-09-18",
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )

    assert cuerpo["grouped_by"] is None
    assert cuerpo["groups"] == []
    assert len(cuerpo["activities"]) == 1
    parada = cuerpo["activities"][0]
    assert parada["purpose"] == "client_visit"
    assert parada["context_reference"] == "ABC Manufacturing"
    assert parada["notes"] == "Pidió 4 más"
    assert parada["outcome_label"], "el resultado se lee con su etiqueta de entonces"
    assert parada["trip_started_at"] and parada["arrived_at"], (
        "la tarjeta de V0.7 separa viaje y permanencia: hacen falta las dos horas"
    )
    assert cuerpo["summary"]["activities"] == 1


# ── Verdad histórica ────────────────────────────────────────────────────────


async def test_una_jornada_que_cruza_medianoche_sigue_en_su_dia(seeded, alpha_client):
    """PR-02: la parada de la 1:00 AM pertenece al día en que se empezó.

    Es el caso que separa el día de negocio del día UTC. Si el explorador
    agrupara por la fecha del evento, esta parada aparecería en el día
    siguiente y el histórico dejaría de cuadrar con la jornada que la contiene.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-EXP-NOCHE")
    hecho = await _jornada_con_parada(alpha_client, seeded)
    dia_de_negocio = date(2026, 9, 18)
    await _fechar_jornada(hecho["jornada"]["id"], dia_de_negocio)

    # El bloque ocurrió pasada la medianoche, ya en el día natural siguiente.
    async with async_session_maker() as session:
        await session.execute(
            text(
                "UPDATE activity_execution SET started_at = :s, ended_at = :e "
                "WHERE trip_id = :t"
            ),
            {
                "s": datetime(2026, 9, 19, 1, 10, tzinfo=timezone.utc),
                "e": datetime(2026, 9, 19, 2, 5, tzinfo=timezone.utc),
                "t": hecho["viaje"]["id"],
            },
        )
        await session.commit()

    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    del_dia = await _explorar(
        alpha_client, range="day", date=dia_de_negocio.isoformat(),
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )
    assert len(del_dia["activities"]) == 1, (
        "la parada de madrugada salió de su día de negocio"
    )

    siguiente = await _explorar(
        alpha_client, range="day", date=(dia_de_negocio + timedelta(days=1)).isoformat(),
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )
    assert siguiente["activities"] == [], (
        "la parada apareció también en el día natural siguiente"
    )


async def test_varias_actividades_son_un_bloque_y_se_ven_todas(seeded, alpha_client):
    """PR-03 y §5: un bloque, varias etiquetas, horas y resultado compartidos.

    Es la única adaptación visible que la instrucción permite, y lo que no se
    puede hacer es fabricar tres historias de ejecución porque se eligieron
    tres actividades. Aquí se comprueba lo segundo: **una** parada.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-EXP-MULTI")
    hecho = await _jornada_con_parada(alpha_client, seeded, actividades=3)
    assert len(hecho["actividades"]) == 3, "hacen falta tres para que el test valga"
    await _fechar_jornada(hecho["jornada"]["id"], date(2026, 9, 18))

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _explorar(
        alpha_client, range="day", date="2026-09-18",
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )

    assert len(cuerpo["activities"]) == 1, (
        "tres actividades seleccionadas produjeron más de una parada"
    )
    parada = cuerpo["activities"][0]
    assert len(parada["activity_labels"]) == 3, "no se enseñan todas las elegidas"
    assert cuerpo["summary"]["activities"] == 1, (
        "el resumen contó etiquetas en vez de paradas"
    )


async def test_el_proposito_y_la_actividad_no_se_confunden(seeded, alpha_client):
    """PR-04: la razón del desplazamiento no es lo que se ejecutó al llegar.

    En un contexto con lista post-llegada —Client Visit— lo que cualifica la
    parada son las actividades seleccionadas, y el propósito viaja aparte. En
    uno sin lista —Office— el dominio sólo tiene el valor del plan, y es ése el
    que se presenta. Mezclarlos en un solo hecho es lo que está prohibido.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-EXP-PR04")
    visita = await _jornada_con_parada(alpha_client, seeded, proposito="client_visit")
    await _fechar_jornada(visita["jornada"]["id"], date(2026, 9, 18))
    oficina = await _jornada_con_parada(
        alpha_client, seeded, proposito="office", referencia="Athens Office"
    )
    await _fechar_jornada(oficina["jornada"]["id"], date(2026, 9, 18))

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _explorar(
        alpha_client, range="day", date="2026-09-18",
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )

    por_proposito = {p["purpose"]: p for p in cuerpo["activities"]}
    assert set(por_proposito) == {"client_visit", "office"}

    con_lista = por_proposito["client_visit"]
    assert con_lista["activity_labels"], "la visita ejecutó actividades"
    assert con_lista["purpose_detail"] is None, (
        "donde hay actividades, el valor del plan no se presenta como si lo fuera"
    )

    sin_lista = por_proposito["office"]
    assert sin_lista["activity_labels"] == [], (
        "el dominio no acepta actividades post-llegada en una visita a oficina"
    )
    assert sin_lista["purpose_detail"], (
        "y entonces lo que cualifica la parada es el valor del plan"
    )


async def test_un_valor_retirado_sigue_leyendose(seeded, alpha_client):
    """PR-05: desactivar un valor no borra la historia que lo usó.

    La etiqueta de la actividad se congela al seleccionarla, así que la parada
    se lee igual después. Y el valor no desaparece de debajo: su clave foránea
    es `RESTRICT`.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-EXP-RETIRADO")
    hecho = await _jornada_con_parada(alpha_client, seeded, actividades=1)
    await _fechar_jornada(hecho["jornada"]["id"], date(2026, 9, 18))

    async with async_session_maker() as session:
        await session.execute(
            text("UPDATE standard_value SET is_active = false WHERE id = :i"),
            {"i": hecho["actividades"][0]},
        )
        await session.commit()

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _explorar(
        alpha_client, range="day", date="2026-09-18",
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )

    parada = cuerpo["activities"][0]
    assert parada["activity_labels"], (
        "la parada perdió su actividad porque el valor se retiró"
    )


async def test_un_bloque_en_curso_no_duerme_como_duracion_cero(seeded, alpha_client):
    """Un bloque abierto no duró nada: todavía no ha terminado.

    Presentarlo como cero sería una afirmación falsa sobre un hecho que sigue
    ocurriendo. La vista lo marca aparte para que la pantalla pueda decir
    `In progress`, como la línea base.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-EXP-ABIERTO")
    hecho = await _jornada_con_parada(
        alpha_client, seeded, terminar=False, cerrar_jornada=False
    )
    await _fechar_jornada(hecho["jornada"]["id"], date(2026, 9, 18))

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _explorar(
        alpha_client, range="day", date="2026-09-18",
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )

    assert cuerpo["summary"]["has_open_activity"] is True
    assert cuerpo["summary"]["activity_seconds"] == 0
    assert cuerpo["activities"][0]["ended_at"] is None


async def test_el_orden_es_determinista(seeded, alpha_client):
    """Dos lecturas seguidas devuelven lo mismo, en el mismo orden."""
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-EXP-ORDEN")
    for _ in range(3):
        hecho = await _jornada_con_parada(alpha_client, seeded)
        await _fechar_jornada(hecho["jornada"]["id"], date(2026, 9, 18))

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    args = dict(
        range="day", date="2026-09-18",
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )
    primera = await _explorar(alpha_client, **args)
    segunda = await _explorar(alpha_client, **args)

    assert [p["activity_execution_id"] for p in primera["activities"]] == [
        p["activity_execution_id"] for p in segunda["activities"]
    ]
    assert len(primera["activities"]) == 3


async def test_un_periodo_sin_registros_responde_vacio_sin_fallar(
    seeded, alpha_client
):
    """FR-08: no hay datos es un estado, no un error ni una fila inventada."""
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-EXP-VACIO")
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    cuerpo = await _explorar(
        alpha_client, range="year", date="2019-05-05",
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )

    assert cuerpo["groups"] == []
    assert cuerpo["activities"] == []
    assert cuerpo["start"] == "2019-01-01"


async def test_cada_supervisor_tiene_su_propia_historia(seeded, alpha_client):
    """Dos supervisores en el mismo periodo no se mezclan."""
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-EXP-A")
    await _perfil_y_vehiculo(
        alpha_client, seeded, unidad="V-EXP-B", usuario="route_admin"
    )
    de_uno = await _jornada_con_parada(alpha_client, seeded, usuario="supervisor")
    await _fechar_jornada(de_uno["jornada"]["id"], date(2026, 9, 18))
    del_otro = await _jornada_con_parada(
        alpha_client, seeded, usuario="route_admin", referencia="North Plant"
    )
    await _fechar_jornada(del_otro["jornada"]["id"], date(2026, 9, 18))

    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    uno = await _explorar(
        alpha_client, range="day", date="2026-09-18",
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )
    otro = await _explorar(
        alpha_client, range="day", date="2026-09-18",
        supervisor_user_id=seeded.alpha.users["route_admin"].id,
    )

    assert len(uno["activities"]) == 1 and len(otro["activities"]) == 1
    assert uno["activities"][0]["context_reference"] == "ABC Manufacturing"
    assert otro["activities"][0]["context_reference"] == "North Plant"
    assert (
        uno["activities"][0]["supervisor_user_id"]
        != otro["activities"][0]["supervisor_user_id"]
    )


# ── Lectura acotada ─────────────────────────────────────────────────────────


async def test_el_numero_de_consultas_no_crece_con_las_paradas(
    seeded, alpha_client, caplog
):
    """§15: nada de N+1. Medido, y sin instrumentar el motor.

    Cómo se mide, y por qué así
    ----------------------------
    La primera versión de un test parecido en RTE07 enganchaba un *listener* al
    motor de SQLAlchemy para contar consultas. Funcionaba aislado y **rompía la
    suite**: tocar el motor global interfiere con el arnés que crea y desecha el
    pool por test. Un test que hace fallar a otros no vale lo que mide.

    Así que se lee lo que la aplicación ya publica: el middleware de rendimiento
    registra `query_count` por petición. Es observación, no instrumentación.

    Lo que se afirma: un día con cinco paradas cuesta **las mismas** consultas
    que un día con una. Si el modelo de lectura pidiera las actividades
    seleccionadas parada por parada, el segundo número sería mayor.
    """
    import logging
    import re

    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-EXP-N1")

    una = await _jornada_con_parada(alpha_client, seeded, actividades=1)
    await _fechar_jornada(una["jornada"]["id"], date(2026, 9, 14))

    for _ in range(5):
        otra = await _jornada_con_parada(alpha_client, seeded, actividades=3)
        await _fechar_jornada(otra["jornada"]["id"], date(2026, 9, 15))

    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    async def consultas_de(dia: str) -> int:
        caplog.clear()
        with caplog.at_level(logging.INFO):
            cuerpo = await _explorar(
                alpha_client, range="day", date=dia,
                supervisor_user_id=seeded.alpha.users["supervisor"].id,
            )
        medidas = [
            int(m.group(1))
            for m in (
                re.search(r"endpoint=\S*activity-explorer\S* .*query_count=(\d+)", r.message)
                for r in caplog.records
            )
            if m
        ]
        assert medidas, "el middleware no registró la petición: la medida no existe"
        return medidas[-1], cuerpo

    pocas, cuerpo_pocas = await consultas_de("2026-09-14")
    muchas, cuerpo_muchas = await consultas_de("2026-09-15")

    # El control de que de verdad hay más que contar en el segundo día.
    assert len(cuerpo_pocas["activities"]) == 1
    assert len(cuerpo_muchas["activities"]) == 5
    assert sum(len(p["activity_labels"]) for p in cuerpo_muchas["activities"]) == 15

    assert muchas == pocas, (
        f"un día con 5 paradas y 15 etiquetas costó {muchas} consultas y uno "
        f"con 1 parada costó {pocas}: el coste crece con las filas"
    )
