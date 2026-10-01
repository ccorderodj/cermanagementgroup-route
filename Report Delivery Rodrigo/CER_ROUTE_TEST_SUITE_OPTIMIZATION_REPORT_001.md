# CER Route — Autodiagnóstico y optimización de la suite de pruebas

**Informe 001** · rama `feature/rte06-field-corrections` · 2026-10-01

Protocolo seguido: Measure → Diagnose → Experiment → Compare → Recommend →
Validate. Ninguna conclusión de este informe viene de otro proyecto CER: todas
las cifras se midieron en este repositorio y en esta máquina, y se dice cuáles
no se pudieron medir.

---

## 1. Current State

La suite tiene **tres niveles**, separados por lo que necesitan para correr. La
separación es real y está declarada: `database_schema` **no** es `autouse` a
propósito, para que el nivel 1 pueda ejecutarse en una máquina sin PostgreSQL.

| Nivel | Ruta | Recogidos | Qué necesita |
|---|---|---|---|
| 1 — unidad / cableado | `tests/` raíz | 111 | nada; lee código fuente, plantillas y TSX |
| 2 — integración | `tests/integration` | 725 | PostgreSQL 16.4 real |
| 3 — navegador | `tests/e2e` | 101 | Edge del sistema + un `uvicorn` vivo |
| **Total** | | **937** | recogidos en 4,24 s |

**Herramientas** (medido con `importlib.metadata`): pytest 9.1.1,
pytest-asyncio 1.4.0 (`asyncio_mode = "auto"`), playwright 1.63.0,
asyncpg 0.31.0, SQLAlchemy 2.0.51.
**No instalados**: `pytest-xdist`, `pytest-cov`, `pytest-timeout`,
`pytest-randomly`.
Configuración: `addopts = "-q --strict-markers"`, `testpaths = ["tests"]`,
marcas `integration` y `browser`.

**Base de datos.** El esquema se reconstruye por `alembic upgrade head`, no por
`create_all`, así que una migración rota rompe la suite. `database_schema` es de
**sesión**: `DROP SCHEMA public CASCADE` + `alembic upgrade` una sola vez.
Recrear la base por test **no** ocurre — era una hipótesis que quedó refutada.

**Limpieza y siembra.** `seeded` es de **función**. Por cada test:

- 7 tablas append-only × 2 `ALTER TABLE … TRIGGER USER` = 14 sentencias
- 36 `DELETE FROM`
- = **50 sentencias de limpieza** + `commit`
- + ~16 `execute()` de siembra (78 capacidades, 3 regiones, 2 compañías, roles,
  13 usuarios)

Está documentado por qué es por test y no por sesión: los tests de aislamiento
crean y borran filas, y compartir estado convertiría un fallo en una cascada.

**Perfil de fixtures** (medido con `pytest --setup-plan`, que no ejecuta nada):

| Nivel 2, 715 tests | | Nivel 3, 101 tests | |
|---|---|---|---|
| `clean_tenant_cache` | 715 (100 %) | `seeded` | 101 (100 %) |
| `_platform_config_vacia` | 715 (100 %) | `live_server` | 101 (100 %) |
| `_function_scoped_runner` | 701 (98 %) | `clean_tenant_cache` | 101 (100 %) |
| `seeded` | 692 (96,8 %) | `_function_scoped_runner` | 101 (100 %) |
| `alpha_client` | 622 (87 %) | `alpha_client` | 20 |

**Hashing.** argon2id con parámetros de producción (64 MiB, `t=3`, `p=4`). El
hash de la contraseña de prueba **ya estaba cacheado** por sesión en un trabajo
anterior. La **verificación** no se puede cachear: la paga cada `login()` real.
Medido en reposo, n=9: **191,7 ms** de mediana. Hay **470** llamadas a
`.login()` en el nivel 2.

**Recursos compartidos entre pruebas.** Clasificados por si sobreviven a un
proceso, que es lo que decide si paralelizar los rompe:

| Recurso | Ámbito | ¿Colisiona entre procesos? |
|---|---|---|
| La base de tests (una sola) | externo | **Sí** — es el bloqueo real |
| `_cache` del resolutor de tenant | en proceso | No |
| `_override` / `_env_backend` de email | en proceso | No |
| `_router` de enrutamiento vial | en proceso | No |
| `Image.MAX_IMAGE_PIXELS` (Pillow) | en proceso | No |
| Puerto de `uvicorn` en e2e | externo | No — se elige libre por test |
| Ficheros de almacenamiento | externo | No evaluado en profundidad |

`docs/DEVELOPMENT_WORKFLOW.md:82` ya lo documenta:
*"One process at a time. Never run two pytest processes against the same test
database: they drop each other's schema."*

**Entorno local.** 4 núcleos lógicos, 31,8 GB de RAM, Windows 11.
PostgreSQL 16.4, `max_connections=100`, `shared_buffers=128MB`, `fsync=on`,
`synchronous_commit=on`.

**CI.** **No hay.** `.gitlab-ci.yml` declara un job con `when: never` a
propósito, documentado en el propio archivo. Todo corre en la máquina del
desarrollador. Por eso ninguna recomendación de este informe fija un número de
workers: se deriva de la capacidad del entorno.

**Certificación completa**, según `docs/DEVELOPMENT_WORKFLOW.md:16`: desde un
clon limpio, `uv sync --frozen`, `npm ci`, `alembic upgrade head` sobre base
vacía, `pytest`, `typecheck`, `lint:ts`, `build:prod`. Es decir, los tres
niveles **más** la cadena de frontend.

---

## 2. Baseline

Medido en reposo, sin nada más corriendo.

| Nivel | Tests | Tiempo | Evidencia |
|---|---|---|---|
| 1 | 111 passed | **13.035 ms** | mediana de 3 ejecuciones |
| 2 | 725 recogidos | **NO MEDIDO completo** | ver nota |
| 2 — subconjunto controlado | 22 passed | **60.196 ms** (2,74 s/test) | exit 0 |
| 3 — muestra de 1 archivo | 9 passed | **110.979 ms** (12,33 s/test) | exit 0 |
| 3 | 101 | **NO MEDIDO completo**; proyección **~20,8 min** | 101 × 12,33 s |

El nivel 3 se midió sobre `tests/e2e/test_route_access_browser.py` (9 recogidos),
con Edge real y un `uvicorn` por test. Su reparto por fases:

| fase | tiempo | % |
|---|---|---|
| setup | 58,22 s | **54,0 %** |
| call | 48,61 s | 45,1 % |
| teardown | 0,88 s | 0,8 % |

**6,47 s de setup por test**, que es el arranque del `uvicorn` más `seeded`.

**Nota sobre el nivel 2.** No tengo el tiempo de pared del nivel 2 completo con
la configuración original. Lo intenté dos veces y lo aborté: la primera vez
porque medí en paralelo y contaminé la medición, la segunda porque proyectaba
más de media hora y ya tenía el ritmo. La proyección desde el subconjunto está
entre **24 y 33 min** según el método de extrapolación, y las dos cifras son
coherentes con que el primer intento pasara de 30 min sin terminar. **No es un
dato medido y no se usa como tal**: la comparación de §4 se apoya en el
subconjunto, que sí está medido en las dos configuraciones.

**Recursos durante el nivel 2** (muestreo cada 5 s, 81 muestras):

- pico de memoria: **206,8 MB** (2 procesos de Python)
- CPU acumulada: **107,6 s en 405 s** de pared = **26,6 % de un núcleo**, 6,6 %
  de una máquina de 4 núcleos

---

## 3. Bottlenecks

Priorizados por impacto medido. Las causas van etiquetadas.

### B-1 · Establecimiento de conexión — `CONFIRMED` · nivel 2 · **90 % del tiempo**

`app/database.py` usaba `NullPool` en modo TEST, así que **cada sesión abría una
conexión física nueva**. Medido sobre 520 conexiones en 90 s de suite:

| magnitud | valor |
|---|---|
| vida media de una conexión | **155,9 ms** |
| trabajo real por conexión (`active_time`) | **6,1 ms** (3,9 %) |
| coste de abrir una conexión (aislado, n=5) | **166,1 ms** |
| conexiones por test | ~15,8 |
| **15,8 × 156 ms** | **2,46 s de los 2,74 s medidos (90 %)** |

El 96 % de la vida de cada conexión era saludo TCP y autenticación.

### B-2 · Setup de fixtures — `CONFIRMED` · nivel 2 · **74,5 % del tiempo restante**

Medido con `--durations=0` sobre el subconjunto, **después** de corregir B-1:

| fase | tiempo | % |
|---|---|---|
| setup | 13,94 s | **74,5 %** |
| call (ejecución real) | 4,05 s | 21,6 % |
| teardown | 0,77 s | 4,1 % |

**634 ms de setup por test.** Es `seeded`: 50 sentencias de limpieza, ~16 de
siembra, y la primera conexión del test.

### B-3 · Recorrido del árbol de fuentes sin podar — `CONFIRMED` · nivel 1

`tests/test_permission_catalog.py` recorría `app/` con `rglob("*.py")`. `app/`
contiene `app/node_modules`: **6.832 directorios y 51.622 ficheros**, para
encontrar **205** de la aplicación. El filtro existente
(`if "components" in path.parts`) no excluía `node_modules`, y la función se
llamaba desde **dos** tests sin caché.

El resultado más útil es contraintuitivo:

| | tiempo | ficheros |
|---|---|---|
| `rglob` original | 2.513 ms | 207 |
| `rglob` + filtro de `node_modules` añadido | **2.539 ms** | 205 |
| recorrido que **no desciende** | **166 ms** | 205 |

**Añadir el filtro no ahorra nada.** El coste es el descenso, no el filtro.

### B-4 · Verificación argon2 — `CONFIRMED` · nivel 2 · **inherente, no se toca**

191,7 ms × 470 `login()` = **90,1 s**. Es el coste de verificar una contraseña
con los parámetros de producción. Bajarlos en los tests aceleraría la suite a
cambio de dejar de ejercitar lo que producción hace. **No se ha tocado.**

### B-5 · Tests de seguridad de migraciones — `CONFIRMED` · inherente

Tras corregir B-1, los más lentos son `test_route_notes_migration_safety.py`
(7 tests) y `test_recovery_accuracy_migration.py`, que ejecutan alembic arriba y
abajo por test: 1,7 s de setup + 2–5 s de call + 1,6 s de teardown cada uno.
Es exactamente lo que prueban. **No se tocan.**

### B-6 · `live_server` de alcance función — `CONFIRMED` · nivel 3

**101 de 101** tests arrancan un `uvicorn` nuevo (intérprete + import de
`app.main`). La razón está documentada y es válida:
`CACHE_TTL_SECONDS = 60` en `app/core/middleware/company_resolver_middleware.py:45`
hace que el proceso de uvicorn cachee la resolución de tenant, mientras `seeded`
resiembra con identificadores nuevos.

Medido: **6,47 s de setup por test**, el 54 % del nivel 3. Sobre 101 tests son
~10,9 min de los ~20,8 min proyectados. Es **la mayor ganancia pendiente de toda
la suite**, y tiene una condición que la convierte en no trivial — ver §6.

### Hipótesis refutadas por medición

Se listan porque descartarlas costó tiempo y evita repetirlo:

| Hipótesis | Medición | Veredicto |
|---|---|---|
| Resolución DNS / IPv6 de `localhost` | `localhost` vs `127.0.0.1`: **−1,9 ms** | **REFUTADA** |
| La suite está limitada por CPU | 26,6 % de un núcleo | **REFUTADA** |
| Los 36 `DELETE` son la causa principal | 226 filas borradas en 15 s | **REFUTADA como principal** |
| Se recrea la base por test | `database_schema` es de sesión | **REFUTADA** |

---

## 4. Experiments

### E1 · Nivel 1 — podar el descenso + cachear el recorrido · **ACEPTADO**

`tests/test_permission_catalog.py`: recorrido que no desciende a
`node_modules`, `components`, `migraciones`, `__pycache__` ni `.venv`, más
`@lru_cache(maxsize=1)` porque dos tests piden lo mismo y el árbol no cambia
durante una ejecución.

| | tests | tiempo |
|---|---|---|
| antes | 111 passed | 13.035 ms |
| después | 111 passed | **11.541 ms** (−11,5 %) |
| solo ese archivo | 7 passed | 5.780 → **3.670 ms** (−36 %) |

0 aserciones cambiadas, 0 tests eliminados. Verifiqué por lectura que nadie muta
el diccionario cacheado (solo `.items()` y `.values()`).

**Hallazgo incidental de correctitud** — mecanismo `CONFIRMED`, riesgo `LIKELY`:
el test parseaba con `ast` dos ficheros `.py` de `node_modules`
(`flatted/python/flatted.py`, `shell-quote/print.py`). Hoy los dos parsean y
ninguno menciona capacidades, así que no fallaba nada — pero **qué** se parseaba
dependía de qué paquetes npm estuvieran instalados, y una dependencia nueva con
un `.py` incompatible habría roto una de las redes de seguridad por un motivo
sin relación con el producto. E1 lo cierra. **Acción operativa: ninguna.**

### E2 · Nivel 2 — pool sin acotar su vida · **RECHAZADO**

Quitar `NullPool` y usar pool, sin más.

| | resultado |
|---|---|
| tiempo | 23.327 ms (2,58x más rápido) |
| **exit** | **1** |
| **errores** | **10 de 22** |

`RuntimeError: Event loop is closed`. **Causa `CONFIRMED`**: `pytest-asyncio`
abre un event loop nuevo por test (`_function_scoped_runner`, presente en
701/715), y una conexión de asyncpg queda atada al loop que la creó; el test
siguiente la hereda del pool con ese loop ya cerrado.

Esto deja una lección que conviene dejar escrita: el comentario que justificaba
`NullPool` daba un motivo **obsoleto** —decía que el pool impediría borrar la
base, cuando `tests/conftest.py::_reset_schema` hace `DROP SCHEMA public
CASCADE` y acto seguido `engine.dispose()`—, y **aun así `NullPool` era
estructural**, por una razón distinta de la documentada. El comentario estaba
mal; la decisión, bien.

### E2b · Nivel 2 — pool con vida de un test · **ACEPTADO**

Pool activo, más una fixture `autouse` que hace `await engine.dispose()` al
cerrar cada test. Acota la vida del pool a un test, que es exactamente la vida
de un event loop: dentro del test se reutiliza la conexión, y al terminar no
queda ninguna que el siguiente pueda heredar con un loop muerto.

Los tamaños del pool son los que el propio proyecto declara en `config.py`
(`DB_POOL_SIZE=3`, `DB_POOL_MAX_OVERFLOW=2`): no se inventa aquí una capacidad
distinta de la ya decidida.

**Subconjunto controlado** — única variable el pool:

| | tests | resultado | tiempo |
|---|---|---|---|
| A — `NullPool` | 22 | 22 passed, exit 0 | **60.196 ms** |
| E2 — pool sin acotar | 22 | **10 ERROR**, exit 1 | 23.327 ms |
| **E2b — pool acotado** | 22 | **22 passed, exit 0** | **22.739 / 23.461 / 22.417 ms** |

**2,65x, funcionalmente equivalente**: 22 passed / 0 failed / 0 skipped en A y
en E2b, y tres ejecuciones consecutivas sin variación de resultado.

**Nivel 2 completo con E2b** (medido):

```
715 passed, 10 skipped in 543.46s (0:09:03)     exit 0
pared: 546.402 ms
```

El techo de 5 conexiones concurrentes **no se agotó** en 715 tests, que era el
riesgo que quedaba de este cambio.

---

### Comprobación de dependencia de orden

Sin instalar nada: un plugin local que invierte el orden de colección.

```
22 passed in 20.28s    exit 0
```

El subconjunto pasa igual del revés. No muestra acoplamiento en esos 22 tests;
no es una afirmación sobre los 725 (ver §6).

---

## 4b. Opciones evaluadas y no implementadas

Lo que queda, con su mejora **estimada** —no medida— y lo que costaría. Se
listan en orden de relación impacto/riesgo.

| Opción | Mejora esperada | Riesgo | Aislamiento | Cobertura | Cambios | Local / CI |
|---|---|---|---|---|---|---|
| **O-1** `uvicorn` compartido en el nivel 3 | **~10,9 min de ~20,8** (54 % del nivel 3) | Medio | Lo mantiene: `seeded` sigue resembrando por test | **La reduce si no se compensa** | Neutralizar `CACHE_TTL_SECONDS` en modo TEST **y añadir** un test que fije el comportamiento de la caché | Igual en los dos |
| **O-2** `synchronous_commit=off` en la base de tests | 99 commits/test × fsync | Bajo | No lo toca | No la toca | Ninguno en el código: `ALTER DATABASE … SET` | **Acción operativa**, por entorno |
| **O-3** Un `TRUNCATE … CASCADE` en vez de 36 `DELETE` | ~35 idas y vueltas/test | Bajo | No lo toca | No la toca | `tests/integration/conftest.py` | Igual en los dos |
| **O-4** Catálogo estático de capacidades a alcance de sesión | 78 inserciones/test | Bajo-medio | Lo reduce: el catálogo deja de reconstruirse | No la toca | `tests/integration/conftest.py` | Igual en los dos |
| **O-5** Paralelizar con `pytest-xdist` | Hasta ~3x en el nivel 2 | **Alto** | **Exige una base por worker** | No la toca | Instalar xdist + `database_schema` por worker | Hoy **incompatible**: una sola base |
| **O-6** Bajar los parámetros de argon2 en tests | ~90 s en el nivel 2 | — | No lo toca | **Deja de ejercitar el coste real** | `auth.py` | — |

**O-6 no se recomienda.** Es el único caso en que la velocidad se paga con
fidelidad de lo que se prueba, que es justo lo que el encargo prohíbe. Se incluye
para que la decisión sea explícita y no por omisión.

**O-1 solo con su test.** Tal cual, cambiaría velocidad por cobertura.

---

## 5. Recommended Strategy

### Desarrollo (mientras se itera)

Los archivos tocados, nivel 1 siempre que se toque cableado o catálogo:

```bash
uv run pytest tests/test_permission_catalog.py tests/test_page_wiring.py   # 3,7 s
uv run pytest tests/integration/test_<lo_que_se_toco>.py
```

### Regresión de impacto

Nivel 1 completo más los módulos afectados. Nivel 1 cuesta **11,5 s**, así que
no hay razón para saltárselo nunca.

### Certificación completa

Los tres niveles más la cadena de frontend, **en serie y un solo proceso**:

```bash
uv run pytest tests/ --ignore=tests/integration --ignore=tests/e2e   # 11,5 s
uv run pytest tests/integration                                      # 9 min 3 s
uv run pytest tests/e2e                                              # ~20,8 min (proyectado)
cd app && npm run check
```

Total de la certificación hoy: **~30 min** de pruebas (11,5 s + 9 min 3 s +
~20,8 min proyectados), más la cadena de frontend. Antes de este trabajo, el
mismo recorrido estaba entre **45 y 54 min** según cómo se extrapole el nivel 2.

### CI

No existe hoy. Cuando se active, el `.gitlab-ci.yml` ya dice cómo y qué debería
correr. Dos condiciones que salen de lo medido:

1. **Una base de datos por worker**, si algún día se paraleliza. Sin eso no es
   negociable: lo prohíbe el propio `DEVELOPMENT_WORKFLOW.md:82`.
2. **El número de workers se deriva, no se fija.** En esta máquina hay 4
   núcleos y argon2 ya pide `parallelism=4` internamente, así que 4 workers
   competirían entre sí dentro del propio hashing. El criterio es
   `min(núcleos − 1, bases_disponibles)`, evaluado en la máquina donde corra, y
   verificando que `max_connections` (hoy 100) cubra `workers × 5`.

### Paralelización: qué haría falta y por qué no se ha hecho

`pytest-xdist` **no está instalado**, y no basta instalarlo. Harían falta bases
por worker y un `database_schema` que las cree. Antes de activarla hay que
verificar explícitamente lo que el protocolo pide; el estado hoy es:

| Comprobación | Estado |
|---|---|
| Colisiones de base de datos | **Bloqueante.** Una sola base compartida |
| Shared state en proceso | Sin riesgo: todos los globales son por proceso |
| Dependencia de orden | **Sin indicios** en 22 tests (orden invertido, 22 passed) |
| Colisiones de sistema de ficheros | No evaluado a fondo |
| Locks | `TRUNCATE`/`DROP SCHEMA` toman ACCESS EXCLUSIVE |
| Cachés compartidas | Sin riesgo entre procesos |
| Recursos externos | Puertos de e2e ya se eligen libres por test |

---

## 6. Risks / Limitations

Lo que queda abierto, dicho como está:

1. **El baseline del nivel 2 completo con `NullPool` NO está medido.** La
   proyección (24–33 min) no es evidencia. La comparación válida es la del
   subconjunto de 22 tests, medida en ambas configuraciones.
2. **Techo del pool.** `pool_size=3 + overflow=2` da 5 conexiones concurrentes.
   Sobrevivió 715 tests, pero un test futuro que mantenga más de 5 sesiones a la
   vez se bloquearía 30 s y luego fallaría. Es un modo de fallo nuevo
   introducido por E2b, y conviene saberlo.
3. **Dependencia de orden: medida solo en 22 tests.** `pytest-randomly` no está
   instalado, así que usé un plugin local que invierte el orden de colección,
   sin añadir dependencias. El subconjunto pasa igual invertido
   (`22 passed, exit 0, 20,28 s`), lo que no muestra acoplamiento **en esos
   22**. No es lo mismo que haberlo descartado en los 725, y el orden invertido
   es una sola permutación, no un muestreo.
4. **Flaky tests: evidencia parcial.** Tres ejecuciones del subconjunto con
   resultado idéntico y una del nivel 2 completo. No es un estudio de
   intermitencia.
5. **B-2 queda sin corregir.** El 74,5 % del tiempo restante del nivel 2 es
   setup de `seeded`. Tres opciones identificadas y **no medidas**: un solo
   `TRUNCATE … CASCADE` en vez de 36 `DELETE`; sacar el catálogo estático de
   capacidades a alcance de sesión; y `synchronous_commit=off` **en la base de
   tests** (ajuste operativo, no de código — con 99 commits por test, cada uno
   espera un fsync).
6. **B-6 queda sin corregir, y con una condición.** Compartir el `uvicorn` entre
   tests exige neutralizar el TTL de la caché de tenant en modo TEST. Comprobé
   que **ningún test cubre hoy el comportamiento de esa caché**, así que hacerlo
   sin más cambiaría velocidad por cobertura. Si se hace, hay que **añadir** un
   test que fije ese comportamiento.
7. **argon2 no se ha tocado** y la recomendación es no tocarlo. Bajar los
   parámetros daría ~90 s en el nivel 2 a cambio de dejar de ejercitar el coste
   real de producción.

---

## 7. Evidence

Comandos para reproducir cada cifra. Entorno: Windows 11, 4 núcleos, 31,8 GB,
PostgreSQL 16.4, `MODE=TEST`.

**Inventario y perfil de fixtures** (no ejecutan tests):

```bash
uv run pytest tests/integration --collect-only -q
uv run pytest tests/integration --setup-plan -q
uv run pytest tests/e2e --setup-plan -q
```

**Nivel 1, antes y después de E1** (mediana de 3, en reposo):

```bash
uv run pytest tests/ --ignore=tests/integration --ignore=tests/e2e
```

**Subconjunto controlado del nivel 2**:

```bash
uv run pytest tests/integration/test_maker_checker.py \
             tests/integration/test_route_role_authority.py
```

**Nivel 2 completo**:

```bash
uv run pytest tests/integration --durations=25
```

**Reparto setup / call / teardown**:

```bash
uv run pytest tests/integration/test_maker_checker.py \
             tests/integration/test_route_role_authority.py --durations=0
```

**Coste de una conexión y del hashing** (scripts de medición, en el scratchpad
de la sesión, no en el repositorio): `asyncpg.connect` × 5 contra el DSN tal
cual y forzando `127.0.0.1`; `verify_password` × 9 con los parámetros de
`app/routers_api/users/auth.py`.

**Ocupación y actividad de PostgreSQL**:

```sql
select sessions, xact_commit, session_time, active_time
from pg_stat_database where datname = current_database();
```

Muestreado al principio y al final de una ventana de 90 s durante la suite.

**Capacidad del entorno**:

```sql
show max_connections; show shared_buffers; show synchronous_commit;
```

### Advertencia metodológica

Dos cifras que di durante el trabajo eran **erróneas** y las corrijo aquí porque
cambiaban el diagnóstico:

- **"12 s por test, 143 min de proyección"** era un artefacto del *buffering* de
  pytest: contaba puntos escritos a bloques en un fichero, no tests
  completados. El dato con reloj es **2,74 s/test**.
- **"80 % del tiempo sin conexión, luego está limitado por CPU"** era una
  inferencia falsa. La CPU estaba al **26,6 % de un núcleo**. El tiempo se iba
  en *abrir* conexiones, que `pg_stat_activity` no cuenta porque todavía no son
  backends.

También conviene registrar que **medí en paralelo al propio baseline** en la
primera vuelta, lo que invalidó la medición que estaba esperando y obligó a
repetirla. Las cifras de este informe se tomaron con la máquina en reposo.

---

## 8. Archivos cambiados

| Archivo | Por qué |
|---|---|
| `tests/test_permission_catalog.py` | E1: poda del descenso + `lru_cache`; deja de parsear `node_modules` |
| `app/database.py` | E2b: pool en modo TEST con los tamaños que declara `config.py`; se documenta por qué el motivo anterior era obsoleto y por qué hacía falta acotar la vida |
| `tests/integration/conftest.py` | E2b: fixture `autouse` que devuelve las conexiones al cerrar el test |
| `tests/e2e/conftest.py` | E2b: importa esa fixture, como ya hacía con `seeded` |
