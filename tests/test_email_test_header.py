"""La cabecera de prueba llega al mensaje SMTP real (RTE-MAIL-TEST-01)."""

from app.core.email.backends import OutgoingEmail, _mensaje


def test_las_cabeceras_extra_van_en_el_mensaje():
    m = _mensaje(
        OutgoingEmail(to="qa@x.com", subject="[TEST] Hola 💪", body="Cuerpo ñ", headers={"X-CER-Route-Test": "activity-email"}),
        "no-reply@x.com",
    )
    assert m["X-CER-Route-Test"] == "activity-email"
    assert m["From"] == "no-reply@x.com" and m["Subject"] == "[TEST] Hola 💪"
    assert "Cuerpo ñ" in m.get_content()


def test_sin_cabeceras_extra_no_cambia_nada():
    m = _mensaje(OutgoingEmail(to="qa@x.com", subject="s", body="b"), "no-reply@x.com")
    assert m["X-CER-Route-Test"] is None
