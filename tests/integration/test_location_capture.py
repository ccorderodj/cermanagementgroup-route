"""RTE-LOC-02 U2: captura periódica de ubicación, servidor.

* Configuración por compañía: apagada por defecto, 300 s, rango 60–3600,
  permiso dedicado a demanda, bloqueo optimista, auditoría, sin cruzar tenants.
* Ingesta: sólo encendida; jornada del usuario autenticado; lotes ≤ 50;
  idempotente; horas, precisión y ventana de la jornada comprobadas.
* Línea de tiempo: unión de eventos y muestras sin tocar `location_fix`; viaje
  de la muestra sólo si es inequívoco.
"""

from __future__ import annotations

import pathlib
import uuid
import pytest

from tests.integration.test_activity_email_delivery import _capacidades, _jornada_en, _utc
from tests.integration.test_activity_emails import _como
from tests.integration.test_org_hierarchy import _ejecutar, _filas

pytestmark = pytest.mark.integration

AJUSTES = "/api/location-capture/settings"
MUESTRAS = "/api/location/samples"
POLITICA = "/api/location/policy"


async def _gestor(seeded, cliente, empresa: str = "alpha"):
    await _capacidades(seeded, "route_admin", "route.locationcapture.manage")
    await cliente.login(getattr(seeded, empresa).users["route_admin"].email)


async def _encender(seeded, cliente, intervalo: int = 300):
    await _gestor(seeded, cliente)
    r = await cliente.put(AJUSTES, json={"enabled": True, "interval_seconds": intervalo, "version": 0})
    assert r.status_code == 200, r.text


def _muestra(minuto_utc: tuple[int, int], precision: str = "12.00", **extra) -> dict:
    return {
        "client_sample_id": str(uuid.uuid4()), "latitude": "33.945512", "longitude": "-83.4204000",
        "accuracy_m": precision, "device_captured_at": _utc(*minuto_utc).isoformat(), **extra,
    }


async def _jornada(seeded, cliente) -> int:
    """Jornada cerrada del supervisor: 13:00–21:00 UTC; viaje 13:05–13:35."""
    return await _jornada_en(cliente, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15),
                             fin_jornada=_utc(21))


# ── Configuración ───────────────────────────────────────────────────────────


async def test_configuracion_apagada_por_defecto_con_permiso_propio(seeded, alpha_client):
    await _como(alpha_client, seeded, "route_admin")
    assert (await alpha_client.get(AJUSTES)).status_code == 403, "nadie la tiene por defecto"
    await _gestor(seeded, alpha_client)
    r = (await alpha_client.get(AJUSTES)).json()
    assert (r["enabled"], r["interval_seconds"], r["version"]) == (False, 300, 0)

    assert (await alpha_client.put(AJUSTES, json={"enabled": True, "interval_seconds": 59, "version": 0})).status_code == 422
    assert (await alpha_client.put(AJUSTES, json={"enabled": True, "interval_seconds": 3601, "version": 0})).status_code == 422
    r = await alpha_client.put(AJUSTES, json={"enabled": True, "interval_seconds": 120, "version": 0})
    assert r.status_code == 200 and (r.json()["enabled"], r.json()["version"]) == (True, 1)
    viejo = await alpha_client.put(AJUSTES, json={"enabled": False, "interval_seconds": 300, "version": 0})
    assert viejo.status_code == 409, "dos ediciones a la vez: la segunda no pisa"
    malo = await alpha_client.put(AJUSTES, json={"enabled": True, "interval_seconds": 300, "version": 1,
                                                 "company_id": 999})
    assert malo.status_code == 422, "la compañía no llega del cuerpo"

    evento = (await _filas("SELECT changes, actor_user_id FROM audit_event "
                           "WHERE entity_type = 'location_capture_setting'"))[0]
    assert evento.changes == {"enabled": {"old": False, "new": True}, "interval_seconds": {"old": 300, "new": 120}}
    assert evento.actor_user_id == seeded.alpha.users["route_admin"].id

    # Quien ejecuta la recibe en la política; otro tenant no se entera.
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    p = (await alpha_client.get(POLITICA)).json()
    assert (p["periodic_capture_enabled"], p["periodic_capture_interval_seconds"]) == (True, 120)
    filas = await _filas("SELECT company_id FROM location_capture_setting")
    assert [f.company_id for f in filas] == [seeded.alpha.id]


# ── Ingesta ─────────────────────────────────────────────────────────────────


async def test_apagada_no_guarda_nada(seeded, alpha_client):
    jornada = await _jornada(seeded, alpha_client)
    r = await alpha_client.post(MUESTRAS, json={"work_session_id": jornada, "samples": [_muestra((14, 0))]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "periodic_capture_disabled"
    assert await _filas("SELECT 1 FROM location_sample") == []


async def test_ingesta_idempotente_validada_y_sin_tocar_eventos(seeded, alpha_client):
    jornada = await _jornada(seeded, alpha_client)
    eventos_antes = len(await _filas("SELECT 1 FROM location_fix"))
    await _encender(seeded, alpha_client)
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    buena = _muestra((14, 0))
    lote = [
        buena,
        _muestra((14, 5), precision="500.00"),                       # peor que 100 m
        _muestra((12, 0)),                                            # antes de la jornada
        _muestra((21, 30)),                                           # después del cierre
        {**_muestra((14, 0)), "device_captured_at": "2099-01-01T00:00:00+00:00"},
        {**_muestra((14, 0)), "device_captured_at": "2020-01-01T00:00:00+00:00"},
    ]
    r = await alpha_client.post(MUESTRAS, json={"work_session_id": jornada, "samples": lote})
    assert r.status_code == 200, r.text
    estados = [(x["status"], x["reason"]) for x in r.json()["results"]]
    assert estados == [
        ("accepted", None), ("rejected", "low_accuracy"), ("rejected", "outside_session"),
        ("rejected", "outside_session"), ("rejected", "future_timestamp"), ("rejected", "stale"),
    ]
    otra = await alpha_client.post(MUESTRAS, json={"work_session_id": jornada, "samples": [buena]})
    assert otra.json()["results"][0]["status"] == "duplicate"

    fila = (await _filas("SELECT user_id, company_id, interval_seconds_applied FROM location_sample"))
    assert [(f.user_id, f.company_id, f.interval_seconds_applied) for f in fila] == [
        (seeded.alpha.users["supervisor"].id, seeded.alpha.id, 300)]
    assert len(await _filas("SELECT 1 FROM location_fix")) == eventos_antes, "location_fix no cambia"

    demasiadas = [_muestra((14, 1)) for _ in range(51)]
    assert (await alpha_client.post(MUESTRAS, json={"work_session_id": jornada, "samples": demasiadas})).status_code == 422
    falso = await alpha_client.post(MUESTRAS, json={"work_session_id": jornada, "samples": [buena], "user_id": 1})
    assert falso.status_code == 422, "ni usuario ni compañía en el cuerpo"


async def test_jornada_ajena_u_otro_tenant_es_404(seeded, alpha_client, beta_client):
    jornada = await _jornada(seeded, alpha_client)
    await _encender(seeded, alpha_client)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)  # ya ejecuta jornadas
    r = await alpha_client.post(MUESTRAS, json={"work_session_id": jornada, "samples": [_muestra((14, 0))]})
    assert r.status_code == 404, "la jornada es de otro usuario"
    await beta_client.login(seeded.beta.users["supervisor"].email)
    r = await beta_client.post(MUESTRAS, json={"work_session_id": jornada, "samples": [_muestra((14, 0))]})
    assert r.status_code in (404, 409), "otro tenant: ni la ve ni la tiene encendida"
    assert await _filas("SELECT 1 FROM location_sample") == []


# ── Línea de tiempo ─────────────────────────────────────────────────────────


async def test_linea_de_tiempo_une_eventos_y_muestras(seeded, alpha_client):
    jornada = await _jornada(seeded, alpha_client)
    await _encender(seeded, alpha_client)
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    en_viaje, fuera = _muestra((13, 20)), _muestra((16, 0))
    await alpha_client.post(MUESTRAS, json={"work_session_id": jornada, "samples": [en_viaje, fuera]})
    viaje = (await _filas("SELECT id FROM trip WHERE work_session_id = :j", j=jornada))[0].id
    # El punto del evento lo captura el navegador; aquí se inserta como lo haría la API.
    await _ejecutar(
        "INSERT INTO location_fix (company_id, work_session_id, event_kind, subject_kind, subject_id, "
        "evidence_level, latitude, longitude, accuracy_m, device_captured_at, server_received_at) "
        "VALUES (:c, :j, 'start_trip', 'trip', :t, 'fresh', 33.9, -83.4, 10, :h, :h)",
        c=seeded.alpha.id, j=jornada, t=viaje, h=_utc(13, 5),
    )

    filas = await _filas(
        "SELECT source, company_id, user_id, trip_id, trip_attribution, captured_at "
        "FROM location_point_timeline WHERE work_session_id = :j ORDER BY captured_at", j=jornada)
    assert {f.source for f in filas} == {"event", "periodic"}
    assert {f.company_id for f in filas} == {seeded.alpha.id}
    assert {f.user_id for f in filas} == {seeded.alpha.users["supervisor"].id}
    periodicas = {f.captured_at: f for f in filas if f.source == "periodic"}
    assert (periodicas[_utc(13, 20)].trip_id, periodicas[_utc(13, 20)].trip_attribution) == (viaje, "interval")
    assert periodicas[_utc(16, 0)].trip_id is None, "fuera de cualquier viaje: sin viaje"
    eventos = [f for f in filas if f.source == "event" and f.trip_id is not None]
    assert eventos and all(f.trip_attribution == "event" for f in eventos)



def test_ningun_calculo_de_millas_ni_routing_lee_las_muestras():
    raiz = pathlib.Path("app/routers_api")
    for modulo in ("mileage", "activityexplorer", "reports", "live", "location"):
        for fichero in (raiz / modulo).rglob("*.py"):
            texto = fichero.read_text(encoding="utf-8")
            assert "location_sample" not in texto and "location_point_timeline" not in texto, fichero


# ── Aviso, una sola vez por persona ─────────────────────────────────────────


async def test_aviso_una_sola_vez_por_persona(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    assert (await alpha_client.get(POLITICA)).json()["periodic_notice_pending"] is False, "apagada: no hay aviso"

    await _encender(seeded, alpha_client)
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    assert (await alpha_client.get(POLITICA)).json()["periodic_notice_pending"] is True
    assert (await alpha_client.post("/api/location-capture/notice/ack")).status_code == 204
    assert (await alpha_client.post("/api/location-capture/notice/ack")).status_code == 204, "idempotente"
    assert (await alpha_client.get(POLITICA)).json()["periodic_notice_pending"] is False, "no se repite"

    filas = await _filas("SELECT user_id, notice_version FROM location_notice_ack")
    assert [(f.user_id, f.notice_version) for f in filas] == [(seeded.alpha.users["supervisor"].id, 1)]

    # Otra persona de la misma compañía todavía no lo vio.
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    assert (await alpha_client.get(POLITICA)).json()["periodic_notice_pending"] is True
