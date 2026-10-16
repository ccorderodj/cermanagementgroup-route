"""
El planificador de plataforma (S7).

Qué hace
--------
* Comprueba todo lo configurado cada `health_checks.interval_minutes`, y avisa
  por correo si algo pasa de sano a fallido.
* Re-escanea la evidencia en cuarentena cada quince minutos.
* Avisa, a diario, de las credenciales que caducan en menos de 30 días.
* Admite más jobs (`register`): formularios oficiales y retención los añaden.

Una sola instancia
------------------
Con varias réplicas, cada una tendría su planificador y todo se haría varias
veces: tres correos por cada fallo. Sólo trabaja la instancia que tiene el
candado consultivo de PostgreSQL (`pg_try_advisory_lock`), mantenido en una
conexión dedicada mientras vive. Si esa instancia muere, la conexión se cierra,
el candado se libera y otra lo toma en el siguiente minuto.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from app.config import settings
from app.logger import logger

LOCK_ID = 7_310_012


class PlatformScheduler:
    def __init__(self) -> None:
        self._scheduler = None
        self._lock_connection = None
        self.leader = False
        self._last_scheduled_checks: datetime | None = None
        self._extra: list[tuple[str, Callable[[], Awaitable[None]], dict]] = []

    def register(self, name: str, job: Callable[[], Awaitable[None]], **trigger) -> None:
        """Añade un job que sólo corre en la instancia líder."""
        self._extra.append((name, job, trigger))

    async def try_leadership(self, dsn: str) -> bool:
        if self.leader:
            return True
        import asyncpg

        try:
            conexion = await asyncpg.connect(dsn)
            if await conexion.fetchval("SELECT pg_try_advisory_lock($1)", LOCK_ID):
                self._lock_connection, self.leader = conexion, True
                logger.info("SCHEDULER | this instance is the leader")
            else:
                await conexion.close()
        except Exception:
            logger.warning("SCHEDULER | could not reach the database for leadership", exc_info=True)
        return self.leader

    async def release(self) -> None:
        if self._lock_connection is not None:
            try:
                await self._lock_connection.execute("SELECT pg_advisory_unlock($1)", LOCK_ID)
            finally:
                await self._lock_connection.close()
        self._lock_connection, self.leader = None, False

    def _only_leader(self, job: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        async def envuelto() -> None:
            if not self.leader:
                return
            try:
                await job()
            except Exception:
                logger.exception("SCHEDULER | job failed")
        return envuelto

    async def _heartbeat(self) -> None:
        from app.core.platform.diagnostics import write_heartbeat
        from app.database import libpq_dsn

        dsn = libpq_dsn()
        if await self.try_leadership(dsn):
            await write_heartbeat()

    async def _scheduled_checks(self) -> None:
        from app.core.platform import diagnostics
        from app.core.platform.config_service import platform_config

        await platform_config.ensure_fresh()
        politica = platform_config.policy("health_checks")
        if not politica.get("enabled", True):
            return
        ahora = datetime.now(timezone.utc)
        intervalo = timedelta(minutes=int(politica.get("interval_minutes", 60)))
        if self._last_scheduled_checks and ahora - self._last_scheduled_checks < intervalo:
            return
        self._last_scheduled_checks = ahora
        await diagnostics.run_all(trigger="scheduled", alert=True)

    async def _secret_expiry(self) -> None:
        from sqlalchemy import select

        from app.core.platform.diagnostics import notify_platform_admins
        from app.core.platform.models import PlatformIntegration, PlatformSecret
        from app.database import async_session_maker

        limite = datetime.now(timezone.utc) + timedelta(days=30)
        async with async_session_maker() as session:
            filas = (
                await session.execute(
                    select(PlatformIntegration.key, PlatformSecret.name, PlatformSecret.expires_at)
                    .join(PlatformIntegration, PlatformIntegration.id == PlatformSecret.integration_id)
                    .where(PlatformSecret.expires_at.is_not(None), PlatformSecret.expires_at <= limite)
                )
            ).all()
        if filas:
            lineas = "\n".join(f"- {k} / {n}: expires {e:%Y-%m-%d}" for k, n, e in filas)
            await notify_platform_admins(
                subject=f"{settings.APP_NAME} — credentials expiring soon",
                body=f"These credentials expire within 30 days. Replace them in Settings:\n\n{lineas}\n",
            )

    async def _deliver_webhooks(self) -> None:
        from app.core.integration.webhooks import deliver_due

        informe = await deliver_due()
        if informe.delivered or informe.failed:
            logger.info(
                "SCHEDULER | webhooks delivered=%s retried=%s failed=%s",
                informe.delivered, informe.retried, informe.failed,
            )

    async def _purge_idempotency(self) -> None:
        from app.core.integration.idempotency import purge_expired

        await purge_expired()

    async def start(self) -> None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        ahora = datetime.now(timezone.utc)
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._scheduler.add_job(self._heartbeat, "interval", minutes=1, next_run_time=ahora,
                                id="heartbeat", max_instances=1, coalesce=True)
        self._scheduler.add_job(self._only_leader(self._scheduled_checks), "interval", minutes=5,
                                next_run_time=ahora + timedelta(seconds=30), id="checks",
                                max_instances=1, coalesce=True)
        # Webhooks salientes pendientes y claves de idempotencia caducadas.
        self._scheduler.add_job(self._only_leader(self._deliver_webhooks), "interval", seconds=30,
                                id="deliver_webhooks", max_instances=1, coalesce=True)
        self._scheduler.add_job(self._only_leader(self._purge_idempotency), "interval", hours=1,
                                id="purge_idempotency", max_instances=1, coalesce=True)
        self._scheduler.add_job(self._only_leader(self._secret_expiry), "cron", hour=7,
                                id="secret_expiry", max_instances=1, coalesce=True)
        for nombre, job, disparador in self._extra:
            self._scheduler.add_job(self._only_leader(job), id=nombre, max_instances=1,
                                    coalesce=True, **disparador)
        self._scheduler.start()
        logger.info("SCHEDULER | started")

    async def shutdown(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
        await self.release()


platform_scheduler = PlatformScheduler()
