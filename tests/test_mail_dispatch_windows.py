"""Ventanas y textos de los correos reales, sin base (RTE-MAIL-CP4-01/02)."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest

from app.config import settings
from app.routers_api.activityemails import delivery, real_reports


@pytest.mark.parametrize(
    ("zona", "dia", "esperado_utc"),
    [
        # Dos zonas distintas el mismo día.
        ("America/New_York", date(2026, 10, 14), datetime(2026, 10, 14, 16, 0, tzinfo=timezone.utc)),
        ("America/Chicago", date(2026, 10, 14), datetime(2026, 10, 14, 17, 0, tzinfo=timezone.utc)),
        # Los dos cambios de horario de 2026 en Nueva York: el mediodía local
        # sigue siendo las 12:00 locales, no una hora UTC fija.
        ("America/New_York", date(2026, 3, 8), datetime(2026, 3, 8, 16, 0, tzinfo=timezone.utc)),
        ("America/New_York", date(2026, 11, 1), datetime(2026, 11, 1, 17, 0, tzinfo=timezone.utc)),
        ("America/New_York", date(2026, 11, 2), datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)),
    ],
)
def test_mediodia_local_en_zonas_y_cambios_de_horario(zona, dia, esperado_utc):
    assert real_reports._local(dia, real_reports.MEDIODIA, zona) == esperado_utc


def test_lineas_motivacionales_en_singular_y_plural():
    filas = [{"purpose": "client_visit"}, {"purpose": "client_visit"}, {"purpose": "recruiting"}, {"purpose": "office"}]
    assert real_reports._lineas(filas) == [
        "- 2 visitas a clientes.",
        "- 1 actividad de reclutamiento.",
        "- 1 gestión de oficina.",
    ]


def test_bloque_semanal():
    filas = [{"purpose": "client_visit"}] * 3 + [{"purpose": "recruiting"}, {"purpose": "office"}]
    assert real_reports._semana(filas) == (
        "Tu semana hasta hoy:\n5 actividades realizadas durante la semana en visitas, "
        "reclutamiento y gestiones operativas."
    )
    assert "Sin actividades" in real_reports._semana([])


def test_destino_enmascarado():
    assert delivery.enmascarar("mgarcia@cermanagementgroup.com") == "m***a@cermanagementgroup.com"
    assert delivery.enmascarar("a@x.com") == "a***@x.com"


def test_hora_maxima_estrategica_sin_elegir_y_elegida(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_STRATEGIC_CUTOFF", "")
    assert real_reports._corte_estrategico() is None
    monkeypatch.setattr(settings, "MAIL_STRATEGIC_CUTOFF", "18:30")
    assert real_reports._corte_estrategico() == time(18, 30)


def test_tipos_habilitados_para_envio_real(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_REAL_SEND_TYPES", "")
    assert not delivery._habilitado("midday_motivation")
    monkeypatch.setattr(settings, "MAIL_REAL_SEND_TYPES", " midday_motivation , strategic_midday_report")
    assert delivery._habilitado("midday_motivation") and not delivery._habilitado("end_of_day_recognition")


def test_todo_apagado_por_defecto():
    from app.config import Settings

    campos = Settings.model_fields
    assert campos["MAIL_AUTOMATION_ENABLED"].default is False
    assert campos["MAIL_AUTOMATION_DRY_RUN"].default is True
    assert campos["MAIL_REAL_SEND_TYPES"].default == ""
    assert campos["MAIL_STRATEGIC_CUTOFF"].default == ""
