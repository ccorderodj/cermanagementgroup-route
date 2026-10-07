# Migraciones automáticas en DigitalOcean App Platform

Runbook extraído de la puesta en marcha del ambiente de prueba de CER Route
(octubre de 2026). Está escrito para **replicarse en otro proyecto**: la primera
mitad es la configuración, la segunda es lo que costó llegar a ella.

El objetivo es uno: que `alembic upgrade head` corra **solo**, antes de que el
código nuevo empiece a atender peticiones, y que un fallo de la migración
**impida** el despliegue en lugar de dejar el esquema a medias.

---

## 1. La decisión: job del App Spec, no GitLab CI

| Razón | Detalle |
| --- | --- |
| Credenciales | El job hereda las variables de entorno de la app. Con CI habría que duplicar la contraseña de la base como variable del pipeline |
| Orden | La plataforma garantiza la secuencia: migra → si va bien, entra el código nuevo. En CI el orden hay que construirlo |
| Fallo | Si el job falla, **el release no sale**: sigue sirviendo la versión anterior contra el esquema anterior |
| Convivencia | Con `deploy_on_push: true` no hay carrera entre el pipeline y el despliegue. Con CI habría que apagar el auto-deploy |

### Cuándo sí conviene GitLab

El job del spec corre **durante** el despliegue. No sirve como puerta previa.
GitLab es mejor cuando hace falta:

- correr la suite **antes** de fusionar (eso el spec no lo puede hacer);
- revisar el SQL de la migración con `alembic upgrade --sql` y que alguien lo apruebe;
- migrar bases que no pertenecen a la app (otro proyecto, otro proveedor);
- un orquestado con pasos manuales entre medias.

En la práctica conviven: GitLab valida antes de fusionar, el spec migra al desplegar.

---

## 2. La configuración final

En el App Spec, al mismo nivel que `services:`:

```yaml
jobs:
- build_command: |
    # el mismo build_command que el servicio web
  environment_slug: python
  gitlab:
    branch: dev
    deploy_on_push: true
    repo: tu-grupo/tu-repo
  instance_count: 1
  instance_size_slug: apps-s-1vcpu-0.5gb
  kind: PRE_DEPLOY
  name: migrate
  run_command: |
    set -e
    python -m alembic -c app/alembic.ini current
    python -m alembic -c app/alembic.ini upgrade head
    python -m app.db.scripts.converge
  source_dir: /
```

Notas:

- **El esquema no es lo unico que un despliegue tiene que llevar al dia.**
  Alembic lleva las tablas; `converge` lleva la **configuracion**: las
  capacidades y sus concesiones a los roles de cada compania, los valores
  estandar de cada una, y la integracion de routing. Son datos, no esquema, y
  por eso ninguna migracion los toca.

  Se puso aqui despues de que la integracion de routing desapareciera del
  entorno compartido y el kilometraje estuviera **seis dias sin calcular**.
  Vivia unicamente como una fila tecleada en una pantalla, asi que no habia
  nada que la repusiera. Ahora el despliegue deja de ser lo que puede perderla
  y pasa a ser lo que la repone.

  `converge` solo anade, es idempotente y no crea companias ni usuarios.
  Correrlo en cada despliegue no cuesta nada: cuando no hay nada que hacer,
  dice `total de cambios: 0`.

- **`set -e` es obligatorio** con mas de un comando. Sin el, un fallo de
  Alembic no detendria el paso siguiente y el release saldria igual.
- **Sin bloque `envs:`.** Las variables de nivel de app se heredan. Declararlas
  otra vez es una copia que se desincroniza.
- `current` antes de `upgrade` no es decorativo: deja en los logs desde qué
  revisión se partió. Cuando algo sale mal, es la primera pregunta.
- `kind: PRE_DEPLOY` es lo que da la garantía de orden. `POST_DEPLOY` migraría
  con el código nuevo ya sirviendo tráfico contra el esquema viejo.
- El job replica el `build_command` del servicio porque necesita las mismas
  dependencias de Python. Si el build del front es caro y el job no lo usa, se
  puede recortar.

---

## 2bis. La variable que repone la integracion de routing

```yaml
envs:
- key: ROUTE_TOMTOM_API_KEY
  scope: RUN_TIME
  type: SECRET
  value: EV[1:...]        # cifrada por DigitalOcean
```

`scope: RUN_TIME` basta: un job corre en tiempo de ejecucion, igual que
`DB_PASS`. Y hace falta `PLATFORM_MASTER_KEY`, que ya esta, porque la clave se
guarda **cifrada** en la base y no en claro.

Si la variable esta vacia o no existe, `converge` **no toca la integracion**.
Es lo correcto para un entorno que usa un motor auto-alojado por
`ROUTE_ROUTING_URL`, o que todavia no ha elegido proveedor.

Y nunca sobrescribe una integracion existente: si un administrador eligio otro
proveedor en la pantalla, esa decision manda. Esto repone lo que falta; no
corrige lo que hay.

---

## 3. Prerrequisitos de código

Dos cambios. Ninguno es específico de DigitalOcean; los dos hacen falta en
cualquier Postgres gestionado al que se llegue por IP pública.

### 3.1. Poder pedir TLS

La URL se construía sin ninguna opción de cifrado. Se añadió un ajuste
**vacío por defecto**:

```python
#: Modo TLS de la conexión. Vacío deja la conexión sin cifrar.
#: Valores: los de libpq —`require`, `verify-ca`, `verify-full`—. En una
#: base gestionada accesible por internet, `require` es el mínimo.
DB_SSL: str = ""
```

Y se aplica **sólo a la conexión por TCP**:

```python
else:
    # El cifrado sólo tiene sentido en la conexión por TCP. La de Cloud
    # SQL va por un socket de Unix del propio host, donde no hay nada
    # que interceptar y `ssl` no aplica.
    cifrado = f"?ssl={self.DB_SSL}" if self.DB_SSL else ""
    self.DATABASE_URL = (
        f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}"
        f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}{cifrado}"
    )
```

Vacío por defecto porque el PostgreSQL de `docker-compose` no ofrece TLS:
exigirlo habría roto el desarrollo local de todo el equipo para arreglar un
ambiente remoto.

### 3.2. El separador en `alembic/env.py`

`env.py` concatena `async_fallback=True` a la URL **ya construida**. Con un `?`
fijo, la primera URL que trajera query string quedaba malformada:

```python
_SEPARADOR = "&" if "?" in RESOLVED_DATABASE_URL else "?"
config.set_main_option(
    "sqlalchemy.url", f"{RESOLVED_DATABASE_URL}{_SEPARADOR}async_fallback=True"
)
```

Este arreglo previene un fallo que **todavía no había ocurrido**: en cuanto
`DB_SSL=require` añade `?ssl=require`, sin el separador condicional la migración
falla por una URL inválida, un motivo que no tiene nada que ver con la
migración. Buscarlo a ciegas cuesta horas.

> Si el proyecto usa `settings.DATABASE_URL` en `env.py`, revisar que no sea la
> URL de desarrollo cuando se corre en modo test. En CER Route `env.py` importa
> la URL **ya resuelta** de `app/database.py` precisamente por eso.

### 3.3. Los tests que lo fijan

`tests/test_database_url.py` cubre las dos mitades: que sin `DB_SSL` la URL es
exactamente la de antes, y que con `DB_SSL` **sigue siendo válida al añadirle lo
que alembic le añade**. Se instancia `Settings(**entorno)` directamente.

> Lección de ese archivo: la primera versión reimportaba `app.config`
> borrándolo de `sys.modules`, y eso dejó sin estado a módulos que otros tests
> ya tenían cargados — cinco empezaron a fallar. Instanciar el objeto basta.

---

## 4. Los obstáculos, en el orden en que aparecieron

Cuatro despliegues fallidos. Esto es la parte que ahorra tiempo.

### 4.1. `SECRET_KEY` demasiado corta

```
SECRET_KEY tiene 23 caracteres; se exigen al menos 32
```

Rotar los secretos sin mirar sus restricciones cuesta un despliegue.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 4.2. `PLATFORM_MASTER_KEY` con formato inválido

Debe ser **exactamente 32 bytes en base64url**. El proyecto trae el generador:

```bash
python -m app.core.platform.secrets generate
```

**Antes de rotarla, comprobar qué cifra.** Si hay secretos de integración
guardados y se pierde la llave, son irrecuperables. En este caso había `0`, así
que no hubo daño — pero el radio de impacto se mide **antes**, no después.

> Y si la llave aparece en un chat, un ticket o una captura: está quemada.
> Generarla en la máquina donde se va a usar.

### 4.3. El Postgres gestionado exige TLS desde IPs públicas

```
no pg_hba.conf entry for host "<ip-publica>", user "doadmin", no encryption
```

**Lo más engañoso de todo.** El servicio web funcionaba perfectamente porque su
salida va por la red interna del proveedor, donde la misma base acepta
conexiones sin cifrar. El job de migraciones sale por IP pública, donde el
`pg_hba.conf` del gestionado sólo admite `hostssl`.

Es decir: la falta de la opción TLS **sólo se manifestaba en un camino**, que es
la peor forma de descubrir que falta una opción.

Arreglo: `DB_SSL=require` como variable de la app.

### 4.4. La contraseña no coincidía

```
InvalidPasswordError: password authentication failed for user "doadmin"
```

Al rotar la contraseña se cambió la variable de la app pero **no la base**.

**Este error es una buena noticia**: si el mensaje pasa de `no encryption` a
`password authentication failed`, el TLS ya funciona y el problema es otro. Se
resolvió reiniciando la contraseña del usuario desde el panel y poniendo el
valor real en `DB_PASS`.

---

## 5. La técnica que desbloqueó todo

El visor de logs devolvía `[Error] historic logs` en los despliegues fallidos.
**No se podía leer el error que había que arreglar.**

La solución: hacer que el job **nunca falle**, pero imprima todo. Los logs de un
despliegue **exitoso** sí se leen.

```yaml
  run_command: |
    echo "=== DIAGNOSTICO INICIO ==="
    python -c "import sys; print('PY', sys.version)"
    python -c "import alembic; print('ALEMBIC', alembic.__version__)"
    python -c "import os; print('DB_HOST', os.environ.get('DB_HOST'))"
    python -c "import os; print('DB_PASS definida:', bool(os.environ.get('DB_PASS')))"
    python -c "import app.database; print('URL OK')"
    python -m alembic -c app/alembic.ini current
    echo "=== DIAGNOSTICO FIN ==="
    exit 0
```

Cada línea aísla una capa: intérprete → dependencias → variables →
configuración → conexión. La primera que no imprima es la que falla.

**Nunca imprimir el valor de un secreto**: `bool(...)` responde la pregunta
—¿está definida?— sin filtrarlo a los logs del proveedor.

Salida limpia, al final:

```
=== DIAGNOSTICO INICIO ===
PY 3.13.12 / ALEMBIC 1.19.1 / MODE DEV
DB_PASS definida: True
URL OK
INFO [alembic.runtime.migration] Context impl PostgresqlImpl.
0014_recovery_accuracy (head)
=== DIAGNOSTICO FIN ===
```

> **Quitar el `exit 0` al terminar.** Mientras esté, un fallo real de migración
> deja pasar el despliegue — exactamente la garantía que se quería instalar.

---

## 6. Orden recomendado en un proyecto nuevo

1. **Antes de tocar el spec**: abrir la consola del contenedor del servicio web y
   correr `python -m alembic -c app/alembic.ini current`. Si falla ahí, el job
   también fallará, y ahí los logs se leen.
2. Revisar los dos prerrequisitos de código (§3). El del separador cuesta dos
   líneas y evita un fallo con mensaje engañoso.
3. Añadir el job con el `run_command` de **diagnóstico** (§5).
4. Leer los logs, arreglar lo que salga, repetir.
5. Cuando el diagnóstico salga limpio, poner el `run_command` real (§2).
6. Verificar que un despliegue normal sigue verde **sin la red de seguridad**.

---

## 7. Dos trampas que no son obvias

### 7.1. `asyncpg` crudo no entiende `ssl=`

El dialecto de SQLAlchemy acepta `?ssl=require` en la URL. Una llamada directa a
`asyncpg.connect(dsn)` **lo ignora**: libpq espera `sslmode=`.

Si el proyecto tiene conexiones fuera de SQLAlchemy —un *listener* de `NOTIFY`,
un scheduler que toma un advisory lock— siguen saliendo sin cifrar aunque la URL
principal ya esté arreglada. En CER Route quedan dos:

- `app/core/platform/config_service.py:171`
- `app/core/platform/scheduler.py:83`

Las dos hacen `DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)`
y arrastran el `?ssl=` que asyncpg descarta. El síntoma es degradación, no
caída: reintentos cada 30 s en los logs. El arreglo natural es un helper
compartido en `app/database.py` que traduzca `ssl=` a `sslmode=`, con su test.

**Estado: pendiente.**

### 7.2. `bootstrap` no es idempotente del todo

Correr la siembra inicial dos veces no es inofensivo:

- `seed_permissions` es **segura** y aditiva: sólo añade capacidades nuevas.
- `seed_company` busca la compañía por **subdominio**. Si
  `BOOTSTRAP_COMPANY_SUBDOMAIN` no coincide con el tenant real, no la encuentra,
  intenta crearla y choca contra el índice único por **nombre**:
  `UniqueViolationError ... "company_name_key"`.
- `seed_roles` **re-añade** concesiones que alguien hubiera quitado a mano. Si se
  revocó una capacidad deliberadamente, vuelve.

Todo va dentro de un `async with transaction()`, así que un fallo no deja nada
escrito. Pero si sólo hacen falta los permisos nuevos, llamar a
`seed_permissions` sola y no al bootstrap completo.

---

## 8. Checklist

```
[ ] alembic current funciona desde la consola del contenedor
[ ] DB_SSL existe en config y se aplica sólo a la URL por TCP
[ ] el separador de env.py es condicional
[ ] test que fija la URL con y sin DB_SSL
[ ] SECRET_KEY >= 32 caracteres
[ ] PLATFORM_MASTER_KEY = 32 bytes base64 (radio de impacto comprobado antes de rotar)
[ ] DB_PASS coincide con la contraseña real de la base
[ ] BOOTSTRAP_COMPANY_SUBDOMAIN coincide con el tenant real
[ ] job PRE_DEPLOY con run_command de diagnóstico, logs limpios
[ ] run_command real, sin exit 0
[ ] un despliegue normal pasa verde
[ ] conexiones asyncpg crudas traducidas a sslmode=
[ ] Trusted Sources de la base configuradas (no abierta a todo internet)
```
