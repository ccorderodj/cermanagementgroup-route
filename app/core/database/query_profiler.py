from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class QueryRecord:
    sql: str
    duration_ms: float


@dataclass
class RequestQueryStats:
    query_count: int = 0
    total_db_time_ms: float = 0.0
    queries: list[QueryRecord] = field(default_factory=list)


current_query_stats: ContextVar[RequestQueryStats | None] = ContextVar(
    "current_query_stats",
    default=None,
)


def before_cursor_execute(
    conn,
    cursor,
    statement,
    parameters,
    context,
    executemany,
) -> None:
    context._query_started_at = time.perf_counter()


def after_cursor_execute(
    conn,
    cursor,
    statement,
    parameters,
    context,
    executemany,
) -> None:
    started_at = getattr(
        context,
        "_query_started_at",
        None,
    )

    if started_at is None:
        return

    duration_ms = (
        time.perf_counter() - started_at
    ) * 1000

    stats = current_query_stats.get()

    if stats is None:
        return

    stats.query_count += 1
    stats.total_db_time_ms += duration_ms

    stats.queries.append(
        QueryRecord(
            sql=" ".join(statement.split()),
            duration_ms=duration_ms,
        )
    )