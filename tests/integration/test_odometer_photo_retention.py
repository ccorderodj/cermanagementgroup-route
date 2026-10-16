"""La purga de fotografías de odómetro, y sobre todo lo que **no** toca.

Qué es esto
-----------
No es una política de negocio: es la consecuencia de que el disco del
contenedor sea efímero y el piloto no tenga almacenamiento de objetos. Dado que
la foto se pierde igualmente en el siguiente despliegue, purgarla a propósito
acota el disco y convierte la desaparición en una regla con una hora escrita, en
vez de una sorpresa que depende de cuándo alguien despliegue.

La propiedad que estos tests defienden
---------------------------------------
**Que el paso del tiempo no cambie la naturaleza de la evidencia.** Es tentador
vaciar `storage_key` al borrar el archivo —la fila quedaría "consistente"— y
sería un error con consecuencias de negocio: `confirm_reading` decide con ese
campo si la lectura es fotográfica o manual, así que una confirmación tardía
pasaría a `manual_exception_confirmed` y exigiría una aprobación que nadie pidió,
sólo porque pasó una hora.

Por eso el último test es el importante: comprueba que una evidencia cuya foto
se purgó **sigue confirmándose como fotográfica**.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.core.storage.base import get_storage
from app.database import async_session_maker
from app.routers_api.odometer import jobs as purga
from tests.integration.test_odometer import FOTO, _jornada_con_vehiculo


pytestmark = pytest.mark.integration


async def _subir(cliente, session_id: int, tipo: str = "start"):
    return await cliente.post(
        f"/api/odometer/sessions/{session_id}/{tipo}/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )


async def _clave(seeded, session_id: int, tipo: str = "start") -> str | None:
    async with async_session_maker() as s:
        return await s.scalar(
            text(
                "SELECT storage_key FROM odometer_evidence WHERE company_id = :c "
                "AND work_session_id = :s AND evidence_type = :t"
            ),
            {"c": seeded.alpha.id, "s": session_id, "t": tipo},
        )


async def _envejecer(seeded, session_id: int, minutos: int) -> None:
    """Mueve `captured_at` hacia atrás, que es lo que mira el barrido.

    Se manipula la hora en vez de esperar: el plazo real es de una hora y un
    test que lo aguardara no sería un test.
    """
    async with async_session_maker() as s:
        await s.execute(
            text(
                "UPDATE odometer_evidence SET captured_at = captured_at - "
                "make_interval(mins => :m) WHERE company_id = :c "
                "AND work_session_id = :s"
            ),
            {"m": minutos, "c": seeded.alpha.id, "s": session_id},
        )
        await s.commit()


# ── Sin retención configurada no pasa nada ─────────────────────────────────


async def test_sin_retencion_la_foto_se_conserva(seeded, alpha_client, monkeypatch):
    """El valor por defecto es conservar, y el barrido lo respeta.

    Importa porque `0` es lo que tienen todos los entornos que no activaron
    esto: un barrido que purgara "por si acaso" borraría evidencia en
    despliegues con almacenamiento duradero.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ODOMETER_PHOTO_RETENTION_MINUTES", 0)
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir(alpha_client, jornada["id"])
    await _envejecer(seeded, jornada["id"], 600)

    assert await purga.purge_expired_odometer_photos() == 0

    clave = await _clave(seeded, jornada["id"])
    assert get_storage().exists(clave), "con retención 0 la foto no se toca"


# ── Con retención, se purga lo vencido y sólo lo vencido ───────────────────


async def test_la_foto_vencida_se_retira(seeded, alpha_client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ODOMETER_PHOTO_RETENTION_MINUTES", 60)
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir(alpha_client, jornada["id"])
    clave = await _clave(seeded, jornada["id"])
    assert get_storage().exists(clave)

    await _envejecer(seeded, jornada["id"], 90)
    assert await purga.purge_expired_odometer_photos() == 1

    assert not get_storage().exists(clave), "la foto vencida sigue en el disco"


async def test_la_foto_reciente_no_se_toca(seeded, alpha_client, monkeypatch):
    """El plazo es un plazo, no una excusa para borrar lo que acaba de llegar."""
    from app.config import settings

    monkeypatch.setattr(settings, "ODOMETER_PHOTO_RETENTION_MINUTES", 60)
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir(alpha_client, jornada["id"])
    await _envejecer(seeded, jornada["id"], 30)

    assert await purga.purge_expired_odometer_photos() == 0

    clave = await _clave(seeded, jornada["id"])
    assert get_storage().exists(clave)


async def test_barrer_dos_veces_no_falla(seeded, alpha_client, monkeypatch):
    """Borrar lo que ya no está no es un error.

    Dos barridos solapados llegan a la misma conclusión, y hacer fallar al
    segundo convertiría una carrera inofensiva en ruido en los logs.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ODOMETER_PHOTO_RETENTION_MINUTES", 60)
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir(alpha_client, jornada["id"])
    await _envejecer(seeded, jornada["id"], 90)

    assert await purga.purge_expired_odometer_photos() == 1
    assert await purga.purge_expired_odometer_photos() == 0


# ── Lo que la purga NO puede cambiar ───────────────────────────────────────


async def test_la_fila_conserva_su_clave_y_su_estado(
    seeded, alpha_client, monkeypatch
):
    """Se borra el archivo, no la evidencia."""
    from app.config import settings

    monkeypatch.setattr(settings, "ODOMETER_PHOTO_RETENTION_MINUTES", 60)
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir(alpha_client, jornada["id"])
    await _envejecer(seeded, jornada["id"], 90)
    await purga.purge_expired_odometer_photos()

    async with async_session_maker() as s:
        fila = (
            await s.execute(
                text(
                    "SELECT storage_key, content_hash, captured_at, status "
                    "FROM odometer_evidence WHERE company_id = :c "
                    "AND work_session_id = :s AND evidence_type = 'start'"
                ),
                {"c": seeded.alpha.id, "s": jornada["id"]},
            )
        ).one()

    assert fila.storage_key is not None, (
        "vaciar la clave convertiría una confirmación tardía en manual"
    )
    assert fila.content_hash is not None, "la huella del contenido es historia"
    assert fila.captured_at is not None
    assert fila.status == "pending"


async def test_una_evidencia_purgada_sigue_confirmandose_como_fotografica(
    seeded, alpha_client, monkeypatch
):
    """El test que de verdad importa.

    Si la purga vaciara `storage_key`, esta confirmación pasaría a necesitar
    una excepción aprobada y terminaría como `manual_exception_confirmed`. El
    supervisor se encontraría pidiendo permiso para teclear una lectura de una
    foto que sí hizo, por el único motivo de haber tardado una hora.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ODOMETER_PHOTO_RETENTION_MINUTES", 60)
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir(alpha_client, jornada["id"])
    await _envejecer(seeded, jornada["id"], 90)
    await purga.purge_expired_odometer_photos()

    confirmacion = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "128437.0"},
    )

    assert confirmacion.status_code == 200, confirmacion.text
    cuerpo = confirmacion.json()
    assert cuerpo["status"] == "photo_confirmed", cuerpo
    assert cuerpo["evidence_method"] == "photo", (
        "la hora de la purga no puede cambiar la naturaleza de la evidencia"
    )


async def test_descargar_una_foto_purgada_devuelve_410(
    seeded, alpha_client, monkeypatch
):
    """Un hecho sobre el recurso, no una avería del servidor.

    Antes esto era un 500: `open` levantaba `FileNotFoundError` y nadie lo
    recogía. Con retención, ese caso deja de ser excepcional y pasa a ser el
    normal, así que tiene que decir lo que ocurre. No es 404 porque la
    evidencia existe y conserva su lectura.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ODOMETER_PHOTO_RETENTION_MINUTES", 60)
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir(alpha_client, jornada["id"])

    async with async_session_maker() as s:
        evidencia_id = await s.scalar(
            text(
                "SELECT id FROM odometer_evidence WHERE company_id = :c "
                "AND work_session_id = :s AND evidence_type = 'start'"
            ),
            {"c": seeded.alpha.id, "s": jornada["id"]},
        )

    antes = await alpha_client.get(f"/api/odometer/evidence/{evidencia_id}/photo")
    assert antes.status_code == 200, "la foto se sirve mientras está"

    await _envejecer(seeded, jornada["id"], 90)
    await purga.purge_expired_odometer_photos()

    despues = await alpha_client.get(f"/api/odometer/evidence/{evidencia_id}/photo")
    assert despues.status_code == 410, despues.text
    assert "no longer stored" in despues.json()["detail"]
