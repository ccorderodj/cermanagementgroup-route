"""Reconcilia la configuración que un despliegue debe garantizar.

El problema que cierra
----------------------
Las migraciones llevan el **esquema** al estado que el código espera. Nada
llevaba los **datos de configuración**, y hay tres clases que un despliegue
puede dejar atrás sin que nadie se entere:

* las **capacidades** del catálogo y sus concesiones a los roles. Mordió cuatro
  veces: cada entrega que añade una capacidad deja fuera a los tenants que ya
  existían, y el Administrador deja de ver una pantalla sin que nada falle;
* los **valores estándar** de cada compañía, que sólo se siembran al crearla.
  Todavía no ha mordido, y morderá en cuanto un checkpoint añada una lista;
* la **integración de routing**, que vivía únicamente como una fila tecleada en
  una pantalla. Desapareció del entorno compartido y el kilometraje estuvo seis
  días sin calcular, con 54 viajes terminalizados por un motor que no existía.

La diferencia entre los tres y el esquema es sólo quién los pone. Esto los pone.

Qué hace, y qué **no**
----------------------
* **Sólo añade.** No revoca, no desactiva, no borra y no pisa decisiones que
  alguien haya tomado en una pantalla.
* **Es idempotente.** La segunda ejecución no cambia nada y lo dice.
* **No crea compañías ni usuarios.** Eso es una decisión, no una
  reconciliación, y por eso sigue siendo del `bootstrap`.
* **Deja rastro**: cada cambio queda auditado, sin actor, porque no lo pidió
  una persona desde una pantalla.

Por qué un registro cerrado
---------------------------
`PASOS` es una tupla explícita y hay un test que la cruza contra las funciones
de aprovisionamiento del repositorio. Sin esa comprobación, el siguiente
checkpoint añadiría una siembra nueva, nadie la registraría aquí, y habríamos
movido el olvido un nivel más arriba en vez de eliminarlo. Es el mismo recurso
que `tests/test_public_surface.py` usa con la superficie pública: una lista que
sólo crece cuando alguien la edita a mano, y editarla obliga a justificarla.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from sqlalchemy import select

from app.config import settings
from app.core.db.session import transaction
from app.core.platform import providers as provider_defs
from app.core.platform.audit import record_platform_event
from app.core.platform.models import PlatformIntegration, PlatformSecret
from app.core.platform.secrets import MasterKeyUnavailable, seal
from app.database import async_session_maker
from app.db.model_registry import load_all_models
from app.routers_api.companies.models import Company

# SQLAlchemy resuelve las relaciones por nombre: un script no importa los
# routers, así que hay que registrar los modelos como hace la aplicación.
load_all_models()

#: La integración que el despliegue repone, y con qué proveedor.
CLAVE_ROUTING = "road_routing"
PROVEEDOR_ROUTING = "tomtom"
SECRETO_ROUTING = "api_key"


@dataclass
class Resultado:
    """Lo que hizo un paso. `cambios` en 0 significa que no había nada que hacer."""

    paso: str
    cambios: int = 0
    detalle: list[str] = field(default_factory=list)


async def _capacidades_y_roles() -> Resultado:
    """El catálogo de capacidades y las concesiones de cada rol.

    Reutiliza el alineador que ya existe en vez de copiar su lógica: dos
    implementaciones de la misma alineación acabarían concediendo cosas
    distintas, que es justo lo que este módulo intenta evitar.
    """
    from app.db.scripts.align_role_capabilities import alinear

    resumen = await alinear()
    resultado = Resultado("capacidades y concesiones de rol", resumen.concesiones_anadidas)
    resultado.detalle = [
        f"{sub} · {rol} -> {cap}" for sub, rol, cap in resumen.detalle
    ]
    for sub, rol in resumen.roles_ausentes:
        resultado.detalle.append(
            f"{sub}: el rol '{rol}' no existe (no se crea; es decisión del tenant)"
        )
    return resultado


async def _valores_estandar() -> Resultado:
    """Las listas configurables de cada compañía, para **todas** las compañías.

    `provision_standard_values` siembra sólo lo que falta y no mira
    `deleted_at`: la pregunta es «¿ya sembré esto?», no «¿sigue vivo?». Así un
    valor que un administrador retiró no resucita en cada despliegue.
    """
    from app.routers_api.standardvalues.provisioning import provision_standard_values

    resultado = Resultado("valores estándar por compañía")
    async with async_session_maker() as session:
        companias = (await session.scalars(select(Company).order_by(Company.id))).all()
        for compania in companias:
            parcial = await provision_standard_values(session, company_id=compania.id)
            if parcial.created:
                resultado.cambios += parcial.created
                resultado.detalle.append(
                    f"{compania.subdomain}: {parcial.created} valores"
                )
        await session.commit()
    return resultado


async def _integracion_de_routing() -> Resultado:
    """Repone la integración `road_routing` si desapareció de la base.

    Las tres reglas, en este orden:

    1. **Sin `ROUTE_TOMTOM_API_KEY` no se toca nada.** Un entorno que usa un
       motor auto-alojado por `ROUTE_ROUTING_URL`, o que todavía no tiene
       proveedor, no quiere que un despliegue le invente uno.
    2. **Si la fila existe, se respeta.** Que un administrador haya elegido
       otro proveedor, o la haya deshabilitado a propósito, es una decisión
       suya. Esto repone lo que falta; no corrige lo que hay.
    3. **El secreto se guarda si falta.** Es el caso de la fila que sobrevivió
       pero perdió su credencial — el adaptador no se monta y el síntoma es
       idéntico a no tener integración.

    `verified_at` queda en nulo a propósito: este comando configura, no
    verifica. Quien verifica es el chequeo `road_routing`, pidiendo una ruta
    real, y esa distinción es la que evita que el despliegue se declare sano a
    sí mismo.
    """
    resultado = Resultado("integración road_routing")
    clave = (settings.ROUTE_TOMTOM_API_KEY or "").strip()
    if not clave:
        resultado.detalle.append(
            "sin ROUTE_TOMTOM_API_KEY: no se toca la integración"
        )
        return resultado

    proveedor = provider_defs.BY_KEY[CLAVE_ROUTING].provider(PROVEEDOR_ROUTING)
    config, errores = provider_defs.validate_config(proveedor, {})
    if errores:
        raise RuntimeError(f"configuración de {PROVEEDOR_ROUTING} inválida: {errores}")

    async with transaction() as session:
        fila = await session.scalar(
            select(PlatformIntegration).where(PlatformIntegration.key == CLAVE_ROUTING)
        )
        creada = fila is None
        if creada:
            fila = PlatformIntegration(
                key=CLAVE_ROUTING,
                provider=PROVEEDOR_ROUTING,
                enabled=True,
                config=config,
                version=1,
            )
            session.add(fila)
            await session.flush()
            resultado.cambios += 1
            resultado.detalle.append(
                f"integración creada: {PROVEEDOR_ROUTING}, habilitada"
            )
        elif fila.provider != PROVEEDOR_ROUTING:
            resultado.detalle.append(
                f"ya configurada con '{fila.provider}': no se toca"
            )
            return resultado

        existente = await session.scalar(
            select(PlatformSecret).where(
                PlatformSecret.integration_id == fila.id,
                PlatformSecret.name == SECRETO_ROUTING,
            )
        )
        if existente is None:
            try:
                sellado = seal(
                    integration_key=CLAVE_ROUTING,
                    secret_name=SECRETO_ROUTING,
                    plaintext=clave,
                )
            except MasterKeyUnavailable as fallo:
                raise RuntimeError(
                    f"no se puede cifrar la clave: {fallo}. "
                    "Sin PLATFORM_MASTER_KEY el secreto no se guarda."
                ) from fallo
            session.add(
                PlatformSecret(
                    integration_id=fila.id,
                    name=SECRETO_ROUTING,
                    ciphertext=sellado.ciphertext,
                    nonce=sellado.nonce,
                    key_id=sellado.key_id,
                )
            )
            fila.version += 1
            resultado.cambios += 1
            resultado.detalle.append("clave guardada (cifrada)")

    if resultado.cambios:
        await record_platform_event(
            request=None,
            actor=None,
            action="integration.converged",
            target=f"integration:{CLAVE_ROUTING}",
            changes={"provider": PROVEEDOR_ROUTING, "created": creada},
        )
    return resultado


#: Registro cerrado. Añadir una siembra nueva sin registrarla aquí hace fallar
#: `tests/test_converge_registry.py`, que es lo que impide que el olvido se
#: repita. El orden importa: las capacidades antes que nada que dependa de
#: ellas.
PASOS: tuple[tuple[str, Callable[[], Awaitable[Resultado]]], ...] = (
    ("capacidades y concesiones de rol", _capacidades_y_roles),
    ("valores estándar por compañía", _valores_estandar),
    ("integración road_routing", _integracion_de_routing),
)


async def converger(*, verbose: bool = False) -> list[Resultado]:
    """Ejecuta todos los pasos en orden y devuelve lo que hizo cada uno."""
    resultados: list[Resultado] = []
    for nombre, paso in PASOS:
        resultado = await paso()
        resultados.append(resultado)
        if verbose:
            print(f"\n  {nombre}: {resultado.cambios} cambio(s)")
            for linea in resultado.detalle:
                print(f"    · {linea}")
    return resultados


async def _principal() -> None:
    print("Convergencia de la configuración del despliegue")
    resultados = await converger(verbose=True)
    total = sum(r.cambios for r in resultados)
    print(f"\n  total de cambios: {total}")
    if not total:
        print("  = todo estaba en su sitio.")


if __name__ == "__main__":
    asyncio.run(_principal())
