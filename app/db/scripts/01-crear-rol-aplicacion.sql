-- =============================================================================
-- 01 — Rol de aplicación
-- =============================================================================
-- Crea el usuario maestro DE LA APLICACIÓN, separado del superusuario `postgres`.
--
-- Por qué: hoy la app se conecta como `postgres`, que es superusuario del
-- clúster. Un fallo de la aplicación (o una inyección) tendría permisos para
-- borrar cualquier base, leer cualquier tabla de cualquier BD y modificar roles.
-- El rol de aplicación solo puede tocar lo suyo.
--
-- Reparto de responsabilidades:
--   postgres            -> administración del clúster, respaldos, migraciones
--                          de infraestructura. NO lo usa la aplicación.
--   cer_app    -> dueño del esquema y de todos los objetos de la app.
--                          Es el que va en DATABASE_URL.
--
-- Ejecutar como `postgres` conectado a la base `cer_app`:
--   psql -h localhost -U postgres -d cer_app -f app/db/scripts/01-crear-rol-aplicacion.sql
--
-- IMPORTANTE: la contraseña de abajo es de DESARROLLO. En producción debe
-- generarse una distinta y vivir solo en el gestor de secretos, nunca en git.
-- =============================================================================

\set ON_ERROR_STOP on

-- Idempotente: no falla si el rol ya existe.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cer_app') THEN
        CREATE ROLE cer_app WITH
            LOGIN
            PASSWORD 'cer_app_dev_change_me'
            NOSUPERUSER      -- no puede saltarse ninguna comprobación de permisos
            NOCREATEDB       -- no puede crear ni borrar bases
            NOCREATEROLE     -- no puede crear ni modificar usuarios
            NOREPLICATION
            INHERIT;
        RAISE NOTICE 'Rol cer_app creado.';
    ELSE
        RAISE NOTICE 'Rol cer_app ya existía; no se modifica.';
    END IF;
END
$$;

-- Se le retira a PUBLIC el permiso de conectarse a las bases del clúster.
-- Por defecto PostgreSQL concede CONNECT a PUBLIC en TODAS las bases, así que
-- un rol nuevo puede abrir sesión contra cualquiera de ellas sin que nadie se
-- lo haya dado.
-- Los superusuarios (postgres) se saltan esta comprobación y siguen entrando.
REVOKE CONNECT ON DATABASE cer_app    FROM PUBLIC;

-- Y se le concede explícitamente solo la suya.
GRANT CONNECT ON DATABASE cer_app TO cer_app;

-- Se le retira a PUBLIC el permiso de crear objetos en `public`.
-- Por defecto PostgreSQL deja que cualquier rol con acceso a la base cree
-- tablas ahí, lo que hace imposible razonar sobre quién es dueño de qué.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin
FROM pg_roles
WHERE rolname IN ('postgres', 'cer_app')
ORDER BY rolname;
