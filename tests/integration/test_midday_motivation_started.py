"""El motivacional de mediodía sale con una actividad iniciada antes del corte.

Regla del PO tras MR !118: basta con haber **iniciado** una actividad antes de
las 12:00, terminada o no. Las abiertas se enseñan aparte con su estado al
corte y nunca cuentan como hechas. Fin de jornada sigue pidiendo una
completada.
"""

from __future__ import annotations

import pytest

from app.routers_api.activityemails import delivery
from tests.integration.test_activity_email_delivery import (  # noqa: F401 — fixtures
    MOT_FIN,
    MOT_MEDIODIA,
    ZONA,
    _activar,
    _jornada_en,
    _utc,
    _zona_de_la_compania,
    automatico,
    envio_real,
)
from tests.integration.test_activity_emails_in_progress import _sin_terminar
from tests.integration.test_mail_close_cp1 import MEDIODIA_UTC, _ev

pytestmark = pytest.mark.integration


async def _mediodia(seeded):
    await _activar(seeded, "supervisor", "midday_enabled")
    return (await _ev(seeded, "supervisor", MOT_MEDIODIA, _utc(22))).reporte


async def test_solo_una_en_curso_a_mediodia_sale(seeded, alpha_client, envio_real):
    # 11:40 locales, sigue abierta a las 12:00; ninguna terminada.
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(15, 9), fin_actividad=None,
                      fin_jornada=None)

    reporte = await _mediodia(seeded)
    assert reporte.eligible is True, reporte.reason_code
    assert reporte.activity_count == 0, "cero completadas"
    assert "- 1 actividad en curso." in reporte.body
    assert "visita a cliente" not in reporte.body, "nada se presenta como hecho"


async def test_terminada_a_mediodia_sigue_igual(seeded, alpha_client, envio_real):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(14),
                      fin_jornada=_utc(21))

    reporte = await _mediodia(seeded)
    assert reporte.eligible is True and reporte.activity_count == 1
    assert "- 1 visita a cliente." in reporte.body
    assert "en curso" not in reporte.body and "sin finalizar" not in reporte.body


async def test_una_terminada_y_una_abierta_un_solo_correo(seeded, alpha_client, outbox, automatico):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(14),
                      fin_jornada=_utc(15))
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(15, 9), fin_actividad=_utc(16, 15),
                      fin_jornada=_utc(21))
    await _activar(seeded, "supervisor", "midday_enabled")

    a = await delivery.despachar_vencidos(ahora=MEDIODIA_UTC)
    b = await delivery.despachar_vencidos(ahora=_utc(16, 5))
    assert (a.accepted, b.accepted) == (1, 0), "una sola entrega"
    (correo,) = outbox.outbox
    texto = str(correo.body)
    assert "- 1 visita a cliente." in texto and "- 1 actividad en curso." in texto


async def test_iniciada_a_las_1215_no_cuenta_aunque_se_genere_tarde(seeded, alpha_client, envio_real):
    # Viaje 11:49, actividad 12:15 locales.
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(15, 44), fin_actividad=_utc(17),
                      fin_jornada=_utc(21))

    reporte = await _mediodia(seeded)
    assert (reporte.eligible, reporte.reason_code) == (False, "no_activity")


async def test_sin_actividad_iniciada_nada_cambia(seeded, alpha_client, envio_real):
    await _zona_de_la_compania(seeded, ZONA)
    reporte = await _mediodia(seeded)
    assert (reporte.eligible, reporte.reason_code) == (False, "no_activity")


async def test_jornada_cerrada_sin_terminar_sale_como_sin_finalizar(seeded, alpha_client, envio_real):
    jornada = await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(14),
                                fin_jornada=_utc(15))
    await _sin_terminar(jornada)

    reporte = await _mediodia(seeded)
    assert reporte.eligible is True and reporte.activity_count == 0
    assert "- 1 actividad iniciada sin finalizar." in reporte.body
    assert "en curso" not in reporte.body


async def test_fin_de_jornada_sigue_pidiendo_una_completada(seeded, alpha_client, envio_real):
    jornada = await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(14),
                                fin_jornada=_utc(15))
    await _sin_terminar(jornada)
    await _activar(seeded, "supervisor", "end_of_day_enabled")

    reporte = (await _ev(seeded, "supervisor", MOT_FIN, _utc(15, 20))).reporte
    assert (reporte.eligible, reporte.reason_code) == (False, "no_activity")
