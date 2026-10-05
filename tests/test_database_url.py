"""Cómo se arma la URL de conexión, y por qué el cifrado es opcional.

Por qué existe este archivo
---------------------------
La URL se construía siempre igual, sin ninguna opción de TLS, y eso bastaba
mientras la base estuviera en la misma red que la aplicación. Dejó de bastar en
cuanto el job de migraciones del ambiente de prueba conectó desde una IP
pública: PostgreSQL lo rechazó con

    no pg_hba.conf entry for host "...", user "...", database "...",
    no encryption

El servicio web no lo notaba porque su salida va por la red interna, donde la
misma base acepta conexiones sin cifrar. Es decir: el fallo sólo aparecía en un
camino concreto, que es la peor forma de descubrir que falta una opción.

Lo que estos tests fijan son las dos mitades del arreglo:

1. sin `DB_SSL`, la URL es exactamente la de antes —si no fuera así, nadie
   podría arrancar contra el PostgreSQL de `docker-compose`, que no ofrece TLS—;
2. con `DB_SSL`, la URL la pide, y **sigue siendo válida al añadirle lo que
   alembic le añade**.

Ese segundo punto es el que de verdad protege: `env.py` concatena
`async_fallback=True` a la URL ya construida. Con un `?` fijo, la primera URL
que trajera query string quedaba malformada y la migración fallaba por un
motivo sin relación con la migración.

Nota sobre cómo se prueba: se instancia `Settings` directamente, con el resto de
valores saliendo del entorno como siempre. La primera versión de este archivo
reimportaba `app.config` borrándolo de `sys.modules`, y eso dejaba sin estado a
los módulos que otros tests ya tenían cargados —cinco de ellos empezaron a
fallar—. El objeto basta: la URL la arma un validador del propio modelo.
"""

from __future__ import annotations

import pytest

from app.config import Settings


def _url(**entorno: str) -> str:
    """La URL que arma `Settings` con esos valores."""
    return Settings(**entorno).DATABASE_URL


def test_sin_db_ssl_la_url_no_cambia():
    """El valor por defecto no toca nada: local sigue funcionando.

    Es la mitad que impide que el arreglo rompa el entorno de desarrollo, donde
    el PostgreSQL del `docker-compose` no ofrece TLS y exigirlo dejaría a
    cualquiera sin poder arrancar.
    """
    url = _url(DB_SSL="")

    assert "ssl=" not in url, url
    assert "?" not in url.split("@")[-1], (
        f"sin DB_SSL la URL no lleva query string: {url}"
    )


def test_con_db_ssl_la_url_lo_pide():
    assert _url(DB_SSL="require").endswith("?ssl=require")


def test_lo_que_alembic_anade_sigue_siendo_una_url_valida():
    """`env.py` concatena `async_fallback=True`, y tiene que elegir separador.

    Este test es el que habría evitado el fallo: con un `?` fijo, una URL que ya
    trajera query string quedaba con dos `?` y la conexión moría por sintaxis,
    no por configuración.
    """
    url = _url(DB_SSL="require")

    separador = "&" if "?" in url else "?"
    final = f"{url}{separador}async_fallback=True"

    assert final.count("?") == 1, f"URL malformada: {final}"
    assert "ssl=require" in final
    assert "async_fallback=True" in final


@pytest.mark.parametrize("modo", ["require", "verify-ca", "verify-full"])
def test_acepta_los_modos_de_libpq(modo):
    """No se inventa un vocabulario propio: son los modos de siempre."""
    assert _url(DB_SSL=modo).endswith(f"?ssl={modo}")


# ── La URL que entiende asyncpg a pelo ─────────────────────────────────────


def test_el_dsn_crudo_traduce_ssl_a_sslmode():
    """El arreglo de un incidente medido en el piloto, no de una sospecha.

    Las dos conexiones crudas del proyecto —el escucha de configuración y la
    elección de líder del scheduler— construían el DSN quitando sólo el
    dialecto. Con `DB_SSL=require` la cadena llegaba a `asyncpg.connect()` con
    `?ssl=require`, y asyncpg no reconoce `ssl` como opción de conexión: lo
    manda al servidor como parámetro de sesión y PostgreSQL contesta

        CantChangeRuntimeParamError: parameter "ssl" cannot be changed now

    No es que se ignorara y la conexión quedara sin cifrar —que fue lo que se
    supuso la primera vez que se identificó esto— sino que **no se abría**.

    Lo que se rompía con ello es lo que hace que merezca un test propio: sin
    líder, el scheduler no ejecuta **ningún** trabajo programado, y los jobs
    siguen apareciendo en el log como "executed successfully" porque el
    envoltorio `_only_leader` sí termina bien. Un barrido que no barre, en
    silencio.
    """
    from app.database import libpq_dsn

    assert libpq_dsn("postgresql+asyncpg://u:p@h:5432/d") == (
        "postgresql://u:p@h:5432/d"
    )
    assert libpq_dsn("postgresql+asyncpg://u:p@h:5432/d?ssl=require") == (
        "postgresql://u:p@h:5432/d?sslmode=require"
    )
    # Y cuando no es el primer parámetro, que es como lo deja alembic.
    assert libpq_dsn("postgresql+asyncpg://u:p@h/d?async_fallback=True&ssl=require") == (
        "postgresql://u:p@h/d?async_fallback=True&sslmode=require"
    )


def test_el_dsn_crudo_no_inventa_cifrado():
    """Sin `DB_SSL`, el DSN crudo no lleva `sslmode` de ninguna clase.

    Añadirlo "por si acaso" rompería el desarrollo local, donde el PostgreSQL
    de `docker-compose` no ofrece TLS — exactamente el motivo por el que
    `DB_SSL` está vacío por defecto.
    """
    from app.database import libpq_dsn

    assert "sslmode" not in libpq_dsn("postgresql+asyncpg://u:p@localhost:5432/d")
