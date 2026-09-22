"""
¿Está lista la plataforma para producción? **Una sola respuesta.**

Settings, Diagnostics y el punto del menú de usuario leen esto: una sola
respuesta en vez de que cada pantalla cuente a su manera.

Tres estados de gate
--------------------
* `closed`: demostrado. Una integración sólo lo está si Diagnostics la verificó.
* `open`: falta algo que el equipo o la operación pueden hacer.
* `waiting_cer`: falta una decisión del negocio. No se cierra desde aquí. Una
  aplicación de dominio añade los suyos en `EXTRA_GATES`.

`blocks_production` dice si ese gate impide declarar la plataforma lista.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from app.config import settings
from app.core.platform import providers as provider_defs
from app.core.platform.integration_status import load_status
from app.core.platform.models import PlatformHealthCheck
from app.core.platform.posture import security_posture

CLOSED, OPEN, WAITING_CER = "closed", "open", "waiting_cer"

#: Gates de dominio. Cada uno es `async (session) -> Gate`. La base no trae
#: ninguno: una aplicación registra aquí lo que su dominio exige para producción.
EXTRA_GATES: list = []

_ESTADOS = {
    "not_configured": "Not configured. Choose a provider in Settings.",
    "incomplete": "Configuration is incomplete.",
    "master_key_missing": "Credentials cannot be read: the master key is missing or does not match.",
    "configured": "Configured but not verified. Run Verify.",
    "failing": "It was verified, but the last check failed.",
    "disabled": "Disabled in Settings.",
    "unavailable": "Cannot be configured yet.",
}


@dataclass
class Gate:
    key: str
    title: str
    status: str
    blocks_production: bool
    detail: str
    action: str
    open_decision: str | None = None


@dataclass
class ReadinessReport:
    production_ready: bool
    mode: str
    gates: list[Gate] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {e: sum(1 for g in self.gates if g.status == e) for e in (CLOSED, OPEN, WAITING_CER)}


async def _integration_gate(session, key: str, title: str) -> Gate:
    definicion = provider_defs.BY_KEY[key]
    estado = await load_status(session, definicion)
    lectura = estado.readiness

    if key == "document_storage" and estado.row and estado.row.provider == "local":
        return Gate(key, title, OPEN, True,
                    "Local storage does not support more than one instance. Configure S3-compatible "
                    "storage and migrate the evidence.", "settings", definicion.open_decision)
    if lectura.status == "verified":
        return Gate(key, title, CLOSED, True, "Verified in Diagnostics.", "diagnostics",
                    definicion.open_decision)
    detalle = _ESTADOS.get(lectura.status, lectura.status)
    # Sólo lo incompleto añade qué falta: «not configured» ya dice lo único que
    # falta, y repetirlo se leía «Choose a provider in Settings. Choose a provider.»
    if lectura.missing and lectura.status == "incomplete":
        detalle = f"{detalle} {' '.join(lectura.missing[:3])}"
    return Gate(key, title, OPEN, True, detalle.strip(), "settings", definicion.open_decision)


async def _email_gate(session) -> Gate:
    """El correo tiene dos proveedores posibles (D-coexist): el gate cierra si
    cualquiera de los dos está verificado, porque eso es lo que de verdad
    decide si un correo sale o no -- `get_email_backend` prueba el preferido y
    cae al de respaldo. Exigir los dos verificados repetiría la falla que la
    política de fallback existe para evitar: bloquear un flujo que ya
    funciona por culpa de una credencial que a esa hora no hace falta."""
    definicion = provider_defs.BY_KEY["email"]
    respaldo = provider_defs.BY_KEY["email_fallback"]
    estado = await load_status(session, definicion)
    estado_respaldo = await load_status(session, respaldo)

    if estado_respaldo.readiness.status == "verified" and estado.readiness.status != "verified":
        return Gate("email", "Outbound email", CLOSED, True,
                    "Verified through the fallback provider in Diagnostics.", "diagnostics")

    lectura = estado.readiness
    if lectura.status == "verified":
        return Gate("email", "Outbound email", CLOSED, True, "Verified in Diagnostics.", "diagnostics")
    detalle = _ESTADOS.get(lectura.status, lectura.status)
    if lectura.missing and lectura.status == "incomplete":
        detalle = f"{detalle} {' '.join(lectura.missing[:3])}"
    return Gate("email", "Outbound email", OPEN, True, detalle.strip(), "settings")


async def _checks_gate(session, key: str, title: str, check_keys: tuple[str, ...], detail_ok: str) -> Gate:
    filas = {
        f.capability_key: f
        for f in (
            await session.execute(
                select(PlatformHealthCheck).where(PlatformHealthCheck.capability_key.in_(check_keys))
            )
        ).scalars()
    }
    faltan = [k for k in check_keys if k not in filas]
    if faltan:
        return Gate(key, title, OPEN, True, "Not checked yet. Run all checks in Diagnostics.", "diagnostics")
    malas = [filas[k] for k in check_keys if filas[k].last_status != "healthy"]
    if malas:
        return Gate(key, title, OPEN, True, malas[0].last_detail or "A check is failing.", "diagnostics")
    return Gate(key, title, CLOSED, True, detail_ok, "diagnostics")


async def evaluate(session) -> ReadinessReport:
    gates = [
        await _email_gate(session),
        await _integration_gate(session, "document_storage", "Document storage"),
        await _integration_gate(session, "malware_scanner", "Malware scanning"),
        await _checks_gate(
            session, "credential_encryption", "Credential encryption",
            ("integrity.master_key",), "The master key works and every stored credential decrypts.",
        ),
        await _checks_gate(
            session, "evidence_integrity", "Evidence integrity",
            ("integrity.protection_triggers", "integrity.migrations", "integrity.rbac_catalog"),
            "Protection triggers, schema version and permission catalog all match.",
        ),
    ]

    problemas = [p for p in security_posture() if not p.ok]
    gates.append(
        Gate("security_posture", "Security posture", CLOSED, True,
             "Every setting is production-grade.", "deployment")
        if not problemas
        else Gate("security_posture", "Security posture", OPEN, True,
                  "Not production-grade: " + ", ".join(p.title for p in problemas) + ".", "deployment")
    )

    for fabrica in EXTRA_GATES:
        gates.append(await fabrica(session))

    listo = all(g.status == CLOSED for g in gates if g.blocks_production)
    return ReadinessReport(production_ready=listo, mode=settings.MODE, gates=gates)
