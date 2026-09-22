-- =============================================================================
-- 03 — Base de datos para la suite de tests
-- =============================================================================
-- Crea `cer_app_test`, separada de `cer_app`, y se la entrega al rol de la
-- aplicación.
--
-- Por qué una base aparte y no la de desarrollo: la suite hace
-- `DROP SCHEMA public CASCADE` al empezar y al terminar. Apuntarla a `cer_app`
-- destruiría los datos de desarrollo. `app/config.py` lo impide —falla el
-- arranque si `TEST_DATABASE_URL` coincide con `DATABASE_URL`— pero la
-- separación real es esta.
--
-- Por qué la crea `postgres` y no la propia suite: `cer_app` es
-- NOCREATEDB a propósito (ver 01-crear-rol-aplicacion.sql). Un rol de
-- aplicación que puede crear y borrar bases no es un rol de aplicación.
--
-- Se ejecuta UNA vez, como `postgres`, conectado a cualquier base:
--
--   "D:\PostgreSQL\14\bin\psql.exe" -h localhost -U postgres -d postgres ^
--       -f app/db/scripts/03-crear-base-de-pruebas.sql
--
-- A partir de ahí la suite se encarga sola: vacía el esquema, aplica
-- `alembic upgrade head`, ejecuta y limpia.
--
-- Idempotente: no falla si la base ya existe.
-- =============================================================================

\set ON_ERROR_STOP on

SELECT 'CREATE DATABASE cer_app_test OWNER cer_app'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_database WHERE datname = 'cer_app_test'
)\gexec

-- Igual que en `cer_app`: PUBLIC no se conecta a lo que no es suyo.
REVOKE CONNECT ON DATABASE cer_app_test FROM PUBLIC;
GRANT CONNECT ON DATABASE cer_app_test TO cer_app;

-- El rol de la aplicación necesita poder crear el esquema `public` cada vez
-- que la suite lo borra.
\connect cer_app_test

ALTER SCHEMA public OWNER TO cer_app;
GRANT ALL ON SCHEMA public TO cer_app;
GRANT CREATE ON DATABASE cer_app_test TO cer_app;

SELECT
    d.datname            AS base,
    pg_get_userbyid(d.datdba) AS dueno,
    has_database_privilege('cer_app', d.datname, 'CREATE') AS puede_crear
FROM pg_database d
WHERE d.datname = 'cer_app_test';
