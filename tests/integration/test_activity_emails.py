"""Correos de actividad (RTE-NOT-01): configuración de plantillas y destinatarios.

Lo que se comprueba, contra PostgreSQL:

* la capacidad `route.activityemails.manage` no la trae ninguna plantilla y sin
  ella todo responde 403 (AC-10);
* las dos plantillas nacen con el texto aprobado; guardar persiste por tenant,
  no toca la otra y queda auditado; una versión vieja es 409 (AC-02/03/13);
* validación de variables y bloques (AC-05); vista previa sin escribir nada
  (AC-04); restaurar sólo la elegida (AC-06);
* destinatarios: sólo quien ejecuta jornada y está en el alcance del actor;
  ambos apagados por defecto; interruptores independientes; sin correo válido
  o sin acceso activo no se activa; otro tenant, 404 (AC-07/08/09);
* la base rechaza una preferencia de alguien de otra compañía y un tipo de
  plantilla inventado (invariante 6).
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.routers_api.activityemails import content
from tests.integration.test_org_hierarchy import _ejecutar, _filas, _organigrama

pytestmark = pytest.mark.integration

CAPACIDAD = "route.activityemails.manage"
PLANTILLAS = "/api/activity-emails/templates"
DESTINATARIOS = "/api/activity-emails/recipients"
MEDIODIA = "midday_motivation"
FIN = "end_of_day_recognition"


async def _conceder(seeded, rol: str, empresa: str = "alpha") -> None:
    compania = getattr(seeded, empresa)
    await _ejecutar(
        "INSERT INTO role_permission (role_id, permission_id, is_active, created_at, updated_at) "
        "SELECT :r, id, true, now(), now() FROM permission WHERE name = :n",
        r=compania.roles[rol], n=CAPACIDAD,
    )


async def _como(cliente, seeded, clave: str, empresa: str = "alpha"):
    await cliente.login(getattr(seeded, empresa).users[clave].email)
    return cliente


async def _plantillas(cliente) -> dict[str, dict]:
    r = await cliente.get(PLANTILLAS)
    assert r.status_code == 200, r.text
    return {t["template_type"]: t for t in r.json()}


async def _destinatarios(cliente, **params) -> dict[int, dict]:
    r = await cliente.get(DESTINATARIOS, params={"page_size": 100, **params})
    assert r.status_code == 200, r.text
    return {f["user_id"]: f for f in r.json()["results"]}


async def _eventos(entity_type: str) -> list:
    return await _filas(
        "SELECT action, actor_user_id, changes FROM audit_event WHERE entity_type = :t ORDER BY id",
        t=entity_type,
    )


# ── Autorización ────────────────────────────────────────────────────────────


async def test_sin_la_capacidad_todo_es_403(seeded, alpha_client):
    for actor in ("owner", "admin", "route_admin", "supervisor", "ceo_base"):
        await _como(alpha_client, seeded, actor)
        uid = seeded.alpha.users["supervisor"].id
        respuestas = [
            await alpha_client.get(PLANTILLAS),
            await alpha_client.put(f"{PLANTILLAS}/{MEDIODIA}", json={"subject": "x", "body": "x", "version": 0}),
            await alpha_client.post(f"{PLANTILLAS}/{MEDIODIA}/restore-default", json={"version": 0}),
            await alpha_client.post(f"{PLANTILLAS}/{MEDIODIA}/preview", json={"subject": "x", "body": "x"}),
            await alpha_client.get(DESTINATARIOS),
            await alpha_client.put(f"{DESTINATARIOS}/{uid}", json={"midday_enabled": True, "version": 0}),
        ]
        assert [r.status_code for r in respuestas] == [403] * 6, actor


async def test_sin_sesion_es_401(seeded, alpha_client):
    assert (await alpha_client.get(PLANTILLAS)).status_code == 401


async def test_la_pagina_exige_la_capacidad(seeded, alpha_client):
    await _como(alpha_client, seeded, "route_admin")
    r = await alpha_client.get("/admin/route/activity-emails", follow_redirects=False)
    assert r.status_code in (302, 303, 403)
    await _conceder(seeded, "route_admin")
    r = await alpha_client.get("/admin/route/activity-emails", follow_redirects=False)
    assert r.status_code == 200
    assert 'data-current-page="RouteActivityEmailsPage"' in r.text


async def test_el_superadmin_entra_sin_concesion(seeded, alpha_client):
    await alpha_client.login(seeded.platform_admin.email)
    assert (await alpha_client.get(PLANTILLAS)).status_code == 200


# ── Plantillas ──────────────────────────────────────────────────────────────


async def test_nacen_con_el_texto_aprobado(seeded, alpha_client):
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    t = await _plantillas(alpha_client)
    assert set(t) == {MEDIODIA, FIN}
    for tipo in (MEDIODIA, FIN):
        s = content.spec(tipo)
        assert t[tipo]["subject"] == s.default_subject
        assert t[tipo]["body"] == s.default_body
        assert t[tipo]["is_default"] is True and t[tipo]["version"] == 0
    assert t[MEDIODIA]["schedule_label"] == "12:00 p.m."
    assert {x["token"] for x in t[FIN]["tokens"] if x["required"]} == {"day_activity_block", "week_activity_block"}
    # Nada se escribió para leerlas.
    assert await _filas("SELECT 1 FROM activity_email_template") == []


async def test_guardar_persiste_por_tenant_y_no_toca_la_otra(seeded, alpha_client, beta_client):
    await _conceder(seeded, "route_admin")
    await _conceder(seeded, "route_admin", "beta")
    await _como(alpha_client, seeded, "route_admin")
    body = "¡Hola, {{user_first_name}}! 💪\n\n{{midday_activity_block}}\n\nCER"
    r = await alpha_client.put(
        f"{PLANTILLAS}/{MEDIODIA}", json={"subject": "Ánimo 🌟", "body": body, "version": 0}
    )
    assert r.status_code == 200, r.text
    guardada = r.json()
    assert guardada["subject"] == "Ánimo 🌟" and guardada["body"] == body
    assert guardada["version"] == 1 and guardada["is_default"] is False
    assert guardada["updated_by_name"] == "Route_admin Tester"

    t = await _plantillas(alpha_client)
    assert t[MEDIODIA]["body"] == body, "persiste al recargar"
    assert t[FIN]["is_default"] is True and t[FIN]["version"] == 0, "la otra no cambia"

    await _como(beta_client, seeded, "route_admin", "beta")
    otra = await _plantillas(beta_client)
    assert otra[MEDIODIA]["is_default"] is True, "otro tenant no la ve"

    eventos = await _eventos("activity_email_template")
    assert [e.action for e in eventos] == ["update"]
    assert eventos[0].actor_user_id == seeded.alpha.users["route_admin"].id
    assert eventos[0].changes["subject"] == {"old": content.spec(MEDIODIA).default_subject, "new": "Ánimo 🌟"}


async def test_version_vieja_es_409_sin_perder_nada(seeded, alpha_client):
    await _conceder(seeded, "route_admin")
    await _conceder(seeded, "owner")
    s = content.spec(FIN)
    await _como(alpha_client, seeded, "route_admin")
    primera = await alpha_client.put(
        f"{PLANTILLAS}/{FIN}", json={"subject": "A", "body": s.default_body, "version": 0}
    )
    assert primera.status_code == 200
    # Otra persona guarda sobre la versión 0, que ya no es la actual.
    await _como(alpha_client, seeded, "owner")
    segunda = await alpha_client.put(
        f"{PLANTILLAS}/{FIN}", json={"subject": "B", "body": s.default_body, "version": 0}
    )
    assert segunda.status_code == 409
    assert (await _plantillas(alpha_client))[FIN]["subject"] == "A"


@pytest.mark.parametrize(
    ("body", "fragmento"),
    [
        ("Hola {{user_first_name}}", "activity summary is required"),
        ("{{midday_activity_block}} {{customer_name}}", "Unsupported variable"),
        ("{{midday_activity_block}} {% if %}", "Malformed"),
        ("{{midday_activity_block}} <script>x</script>", "HTML"),
        ("{{midday_activity_block}} https://evil.example", "Links"),
    ],
)
async def test_validacion_por_campo(seeded, alpha_client, body, fragmento):
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    r = await alpha_client.put(f"{PLANTILLAS}/{MEDIODIA}", json={"subject": "Hola", "body": body, "version": 0})
    assert r.status_code == 422
    detalle = r.json()["detail"]
    assert any(d["loc"] == ["body", "body"] and fragmento in d["msg"] for d in detalle), detalle
    assert await _filas("SELECT 1 FROM activity_email_template") == []


async def test_asunto_con_salto_de_linea_y_tipo_desconocido(seeded, alpha_client):
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    body = content.spec(MEDIODIA).default_body
    r = await alpha_client.put(
        f"{PLANTILLAS}/{MEDIODIA}", json={"subject": "Hola\nBcc: x@y.com", "body": body, "version": 0}
    )
    assert r.status_code == 422
    assert any(d["loc"] == ["body", "subject"] for d in r.json()["detail"])
    r = await alpha_client.put(f"{PLANTILLAS}/weekly_digest", json={"subject": "a", "body": "b", "version": 0})
    assert r.status_code == 404


async def test_vista_previa_ficticia_sin_escribir(seeded, alpha_client):
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    s = content.spec(FIN)
    r = await alpha_client.post(f"{PLANTILLAS}/{FIN}/preview", json={"subject": s.default_subject, "body": s.default_body})
    assert r.status_code == 200, r.text
    vista = r.json()
    assert vista["is_sample"] is True and vista["sample_label"] == "Ejemplo / Vista previa"
    assert "Hola, María:" in vista["body"]
    assert "Tu semana hasta hoy:" in vista["body"] and "{{" not in vista["body"]
    assert await _filas("SELECT 1 FROM activity_email_template") == []
    assert await _eventos("activity_email_template") == []
    malo = await alpha_client.post(f"{PLANTILLAS}/{FIN}/preview", json={"subject": "x", "body": "sin bloques"})
    assert malo.status_code == 422


async def test_restaurar_solo_la_elegida(seeded, alpha_client):
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    for tipo in (MEDIODIA, FIN):
        s = content.spec(tipo)
        r = await alpha_client.put(
            f"{PLANTILLAS}/{tipo}", json={"subject": f"Propio {tipo}", "body": s.default_body, "version": 0}
        )
        assert r.status_code == 200
    supervisor = seeded.alpha.users["supervisor"].id
    assert (await alpha_client.put(
        f"{DESTINATARIOS}/{supervisor}", json={"midday_enabled": True, "version": 0}
    )).status_code == 200

    r = await alpha_client.post(f"{PLANTILLAS}/{MEDIODIA}/restore-default", json={"version": 1})
    assert r.status_code == 200, r.text
    assert r.json()["is_default"] is True and r.json()["version"] == 2

    t = await _plantillas(alpha_client)
    assert t[FIN]["subject"] == f"Propio {FIN}", "la otra sigue personalizada"
    assert (await _destinatarios(alpha_client))[supervisor]["midday_enabled"] is True, "destinatarios intactos"
    assert [e.action for e in await _eventos("activity_email_template")] == ["update", "update", "restore_default"]

    vieja = await alpha_client.post(f"{PLANTILLAS}/{FIN}/restore-default", json={"version": 0})
    assert vieja.status_code == 409


# ── Destinatarios ───────────────────────────────────────────────────────────


async def test_lista_quien_ejecuta_jornada_apagados_y_sin_otro_tenant(seeded, alpha_client):
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    filas = await _destinatarios(alpha_client)
    u = seeded.alpha.users
    assert u["supervisor"].id in filas and u["route_admin"].id in filas and u["ceo_base"].id in filas
    # `viewer` y `manager` no ejecutan jornada: no reciben correos de actividad.
    assert u["viewer"].id not in filas and u["manager"].id not in filas
    assert not set(filas) & {x.id for x in seeded.beta.users.values()}
    assert all(not f["midday_enabled"] and not f["end_of_day_enabled"] for f in filas.values())
    assert await _filas("SELECT 1 FROM activity_email_preference") == [], "nadie suscrito por omisión"

    busqueda = await _destinatarios(alpha_client, q="supervisor@alpha")
    assert set(busqueda) == {u["supervisor"].id}


async def test_interruptores_independientes_y_auditados(seeded, alpha_client):
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    uid = seeded.alpha.users["supervisor"].id
    url = f"{DESTINATARIOS}/{uid}"

    r = await alpha_client.put(url, json={"midday_enabled": True, "version": 0})
    assert r.status_code == 200, r.text
    assert r.json()["midday_enabled"] is True and r.json()["end_of_day_enabled"] is False
    r = await alpha_client.put(url, json={"end_of_day_enabled": True, "version": 1})
    assert r.json()["midday_enabled"] is True and r.json()["end_of_day_enabled"] is True
    r = await alpha_client.put(url, json={"midday_enabled": False, "version": 2})
    assert r.json()["midday_enabled"] is False and r.json()["end_of_day_enabled"] is True

    assert (await _destinatarios(alpha_client))[uid]["end_of_day_enabled"] is True, "persiste"
    assert (await alpha_client.put(url, json={"midday_enabled": True, "version": 1})).status_code == 409
    assert (await alpha_client.put(url, json={"version": 3})).status_code == 400

    eventos = await _eventos("activity_email_preference")
    assert len(eventos) == 3
    assert eventos[2].changes == {"midday_enabled": {"old": True, "new": False}}
    # El correo no se acepta como dato: sale de la cuenta.
    assert (await alpha_client.put(url, json={"email": "x@y.com", "version": 3})).status_code == 422


async def test_sin_correo_valido_o_inactivo_no_se_activa(seeded, alpha_client):
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    u = seeded.alpha.users
    await _ejecutar("UPDATE \"user\" SET email = 'sin-dominio' WHERE id = :u", u=u["supervisor"].id)
    await _ejecutar(
        "UPDATE user_company SET is_active = false WHERE user_id = :u AND company_id = :c",
        u=u["ceo_base"].id, c=seeded.alpha.id,
    )
    filas = await _destinatarios(alpha_client)
    assert filas[u["supervisor"].id]["eligible"] is False
    assert filas[u["supervisor"].id]["ineligible_reason"] == "invalid_email"
    assert filas[u["ceo_base"].id]["ineligible_reason"] == "inactive"

    for clave in ("supervisor", "ceo_base"):
        r = await alpha_client.put(f"{DESTINATARIOS}/{u[clave].id}", json={"midday_enabled": True, "version": 0})
        assert r.status_code == 409, (clave, r.text)
    # Apagar siempre se puede.
    r = await alpha_client.put(f"{DESTINATARIOS}/{u['supervisor'].id}", json={"midday_enabled": False, "version": 0})
    assert r.status_code == 200


async def test_preferencia_de_un_activo_que_se_suspende_deja_de_ser_efectiva(seeded, alpha_client):
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    uid = seeded.alpha.users["supervisor"].id
    await alpha_client.put(f"{DESTINATARIOS}/{uid}", json={"midday_enabled": True, "version": 0})
    await _ejecutar("UPDATE \"user\" SET is_active = false WHERE id = :u", u=uid)
    fila = (await _destinatarios(alpha_client))[uid]
    assert fila["eligible"] is False and fila["ineligible_reason"] == "inactive"


async def test_otro_tenant_o_fuera_de_lista_es_404(seeded, alpha_client):
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    for uid in (seeded.beta.users["supervisor"].id, seeded.alpha.users["viewer"].id, 999999):
        r = await alpha_client.put(f"{DESTINATARIOS}/{uid}", json={"midday_enabled": True, "version": 0})
        assert r.status_code == 404, uid


async def test_un_mando_solo_ve_y_cambia_su_rama(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _conceder(seeded, "COO")
    await _como(alpha_client, seeded, "coo")
    filas = await _destinatarios(alpha_client)
    u = seeded.alpha.users
    assert u["sup_a"].id in filas
    for fuera in ("ceo", "coo", "route_admin", "sales_a", "supervisor"):
        assert u[fuera].id not in filas, fuera
    r = await alpha_client.put(f"{DESTINATARIOS}/{u['sales_a'].id}", json={"midday_enabled": True, "version": 0})
    assert r.status_code == 404
    r = await alpha_client.put(f"{DESTINATARIOS}/{u['sup_a'].id}", json={"midday_enabled": True, "version": 0})
    assert r.status_code == 200


# ── La base ─────────────────────────────────────────────────────────────────


async def test_la_base_rechaza_otro_tenant_y_tipos_inventados(seeded):
    with pytest.raises(IntegrityError):
        await _ejecutar(
            "INSERT INTO activity_email_preference (company_id, user_id) VALUES (:c, :u)",
            c=seeded.alpha.id, u=seeded.beta.users["supervisor"].id,
        )
    with pytest.raises(IntegrityError):
        await _ejecutar(
            "INSERT INTO activity_email_template (company_id, template_type, subject, body) "
            "VALUES (:c, 'weekly_digest', 'a', 'b')",
            c=seeded.alpha.id,
        )
    with pytest.raises(IntegrityError):
        await _ejecutar(
            "INSERT INTO activity_email_template (company_id, template_type, subject, body) "
            "VALUES (:c, 'midday_motivation', E'a\\nBcc: x', 'b')",
            c=seeded.alpha.id,
        )
    await _ejecutar(
        "INSERT INTO activity_email_preference (company_id, user_id) VALUES (:c, :u)",
        c=seeded.alpha.id, u=seeded.alpha.users["supervisor"].id,
    )
    fila = (await _filas("SELECT midday_enabled, end_of_day_enabled FROM activity_email_preference"))[0]
    assert fila.midday_enabled is False and fila.end_of_day_enabled is False
