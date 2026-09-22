#!/bin/bash
# Crea la base de la suite de tests al inicializar el contenedor de PostgreSQL.
#
# La imagen oficial ejecuta todo lo que haya en /docker-entrypoint-initdb.d la
# primera vez que el volumen esta vacio. Asi el entorno de contenedores no
# necesita que el rol de la aplicacion pueda crear bases, que es justo el
# privilegio que se le retiro a proposito.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
    CREATE DATABASE cer_app_test OWNER $POSTGRES_USER;
SQL

echo "Base cer_app_test creada para la suite de tests."
