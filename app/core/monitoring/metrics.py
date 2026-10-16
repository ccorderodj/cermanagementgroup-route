from prometheus_client import Counter, Histogram


API_REQUESTS_TOTAL = Counter(
    "app_api_requests_total",
    "Total number of API requests",
    ["method", "endpoint", "status"],
)


API_REQUEST_DURATION_SECONDS = Histogram(
    "app_api_request_duration_seconds",
    "Total API request duration in seconds",
    ["method", "endpoint"],
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1,
        2.5,
        5,
        10,
    ),
)


API_SQL_QUERIES_PER_REQUEST = Histogram(
    "app_api_sql_queries_per_request",
    "Number of SQL queries executed by one API request",
    ["method", "endpoint"],
    buckets=(
        0,
        1,
        2,
        3,
        5,
        10,
        20,
        30,
        50,
        75,
        100,
        200,
        500,
    ),
)


API_DATABASE_DURATION_SECONDS = Histogram(
    "app_api_database_duration_seconds",
    "Combined SQL execution time per API request",
    ["method", "endpoint"],
    buckets=(
        0.001,
        0.0025,
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1,
        2.5,
        5,
    ),
)