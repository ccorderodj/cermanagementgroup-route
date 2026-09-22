from __future__ import annotations

import time

from fastapi import Request

from app.core.database.query_profiler import (
    RequestQueryStats,
    current_query_stats,
)
from app.core.monitoring.metrics import (
    API_DATABASE_DURATION_SECONDS,
    API_REQUEST_DURATION_SECONDS,
    API_REQUESTS_TOTAL,
    API_SQL_QUERIES_PER_REQUEST,
)
from app.logger import logger


async def query_performance_middleware(
    request: Request,
    call_next,
):
    stats = RequestQueryStats()
    context_token = current_query_stats.set(stats)

    request_started_at = time.perf_counter()
    response = None
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response

    finally:
        request_duration_seconds = (
            time.perf_counter() - request_started_at
        )

        route = request.scope.get("route")
        route_path = getattr(route, "path", None)

        # Se etiqueta con la PLANTILLA de la ruta, no con la URL concreta.
        #
        # Bien:  /api/users/{user_id}
        # Mal:   /api/users/1542
        #
        # Una etiqueta por id convertiria cada usuario en una serie temporal
        # distinta y haria estallar la cardinalidad de las metricas.
        if route_path:
            endpoint = (
                route_path
                if route_path.startswith("/api")
                else f"/api{route_path}"
            )
        else:
            endpoint = "/api/unknown"

        method = request.method

        API_REQUESTS_TOTAL.labels(
            method=method,
            endpoint=endpoint,
            status=str(status_code),
        ).inc()

        API_REQUEST_DURATION_SECONDS.labels(
            method=method,
            endpoint=endpoint,
        ).observe(request_duration_seconds)

        API_SQL_QUERIES_PER_REQUEST.labels(
            method=method,
            endpoint=endpoint,
        ).observe(stats.query_count)

        API_DATABASE_DURATION_SECONDS.labels(
            method=method,
            endpoint=endpoint,
        ).observe(stats.total_db_time_ms / 1000)

        logger.info(
            "API PERFORMANCE | method=%s endpoint=%s status=%s "
            "request_ms=%.2f query_count=%d db_ms=%.2f",
            method,
            endpoint,
            status_code,
            request_duration_seconds * 1000,
            stats.query_count,
            stats.total_db_time_ms,
        )

        current_query_stats.reset(context_token)