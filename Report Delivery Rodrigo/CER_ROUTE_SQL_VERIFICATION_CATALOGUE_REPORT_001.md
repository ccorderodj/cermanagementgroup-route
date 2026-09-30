# CER Route — Catalogo de consultas SQL de verificacion — Reporte 001

**Fecha**: 2026-09-30
**Alcance**: catalogo de consultas SQL que cubren los flujos del sistema, de RTE02 a RTE06
**Estado**: `COMPLETED`
**Rama**: `feature/sql-verification-catalogue`

---

## 1. Status

`COMPLETED` para el alcance pedido: **89 consultas SQL** sobre **12 flujos**,
entregadas como documento y como dos ficheros ejecutables. Las 89 se ejecutaron;
0 errores de SQL.

No cambia ningun comportamiento del sistema. No hay migracion, no hay codigo de
aplicacion tocado, no hay endpoint nuevo. Son tres archivos de documentacion y
herramienta.

---

## 2. Que se entrega

| Archivo | Que es |
|---|---|
| `_cer_delivery/CER_ROUTE_SQL_VERIFICATION_CATALOGUE.md` | El catalogo: cada consulta con lo que prueba, el resultado correcto y lo que significa una fila |
| `_cer_delivery/sql/route_invariantes.sql` | 57 consultas que deben devolver **cero filas**. Se corre como una sola puerta |
| `_cer_delivery/sql/route_informes.sql` | 32 consultas de estado. Requieren `:company_id` |

### Los dos grupos, y por que estan separados

| Grupo | Consultas | Resultado correcto | Una fila significa |
|---|---|---|---|
| Invariante | 57 | cero filas | **un hallazgo** |
| Informe | 32 | cualquiera | estado para leer |

La separacion es operativa: la puerta de invariantes se puede correr sin que
nadie interprete nada —cualquier salida no vacia es un fallo—, mientras que las de
informe exigen un lector que sepa que esta viendo.

### Cobertura por flujo

| Flujo | Consultas | Invariante | Informe |
|---|---|---|---|
| Aislamiento de tenant | 8 | 8 | 0 |
| Usuarios y roles | 8 | 5 | 3 |
| Jornada de trabajo | 7 | 4 | 3 |
| Vigencia de vehiculo | 5 | 3 | 2 |
| Viajes | 8 | 7 | 1 |
| Odometro | 6 | 4 | 2 |
| Actividades | 5 | 3 | 2 |
| Evidencia de ubicacion | 15 | 10 | 5 |
| Kilometraje | 14 | 10 | 4 |
| Correlacion offline | 3 | 1 | 2 |
| Integridad historica | 6 | 2 | 4 |
| Auditoria | 5 | 1 | 4 |

---

## 3. Validacion tecnica

| Comprobacion | Resultado | Evidencia |
|---|---|---|
| Las 89 consultas corren | **PASS** | `89 consultas, 0 con error de SQL` contra PostgreSQL 16.4 |
| `route_invariantes.sql` por `psql` | **PASS** | `exit=0` con `ON_ERROR_STOP=1`, 57 consultas, 57 vacias |
| `route_informes.sql` por `psql` | **PASS** | `exit=0` con `ON_ERROR_STOP=1`, 32 consultas, 20 vacias + 12 con filas |
| Cada consulta de invariante detecta lo que dice | **PASS** | 24 inyecciones: 10 `DETECTA`, 14 `RECHAZA`, **0 `CIEGA`** |
| Migraciones | `NOT APPLICABLE` | no hay cambio de esquema |
| Suite de tests | `NOT RUN` | no se toco codigo de aplicacion; ver §6 |
| `npm run check` | `NOT APPLICABLE` | no hay cambio de frontend |

### El punto importante: por que un cero significa algo

Una consulta de invariante que devuelve cero filas **no prueba nada por si
sola**. Una consulta con un predicado mal escrito devuelve cero filas igual que
una base sana, y sobre un entorno con pocos datos las dos son indistinguibles.

Asi que para las 24 consultas donde importaba se **inyecto la violacion** en una
transaccion que despues se revento, y se comprobo el resultado. Dos veredictos,
los dos validos:

- **`RECHAZA` (14)** — la base no dejo escribir la violacion. La garantia es la
  restriccion; la consulta solo confirma que sigue puesta.
- **`DETECTA` (10)** — nada impide escribirla, se escribio, y la consulta la
  encontro. Aqui **la consulta es la unica defensa**.

Ninguna resulto `CIEGA`. Restricciones que rechazaron, con su `sqlstate` medido:

| Invariante | Restriccion | sqlstate |
|---|---|---|
| Asignaciones de vehiculo solapadas (E5 de CP0) | `ex_vehicle_assignment_no_overlap` | `23P01` |
| Asignacion de duracion cero | `ck_vehicle_assignment_period` | `23514` |
| Un solo punto autoritativo por evento | `uq_location_fix_event` | `23505` |
| Solo tres niveles de evidencia | `ck_location_fix_evidence_level` | `23514` |
| Pareja evento-sujeto valida | `ck_location_fix_event_subject` | `23514` |
| Motivo de Missing del catalogo | `ck_missing_location_reason` | `23514` |
| Un kilometraje por viaje | `uq_trip_mileage_trip` | `23505` |
| Nunca un total parcial publicado | `ck_trip_mileage_calculated_facts` | `23514` |
| Provenance completa | `NOT NULL` en `trip_mileage_segment` | `23502` |
| Un viaje vivo por jornada | `uq_trip_one_non_terminal` | `23505` |
| Una jornada activa por supervisor | `uq_work_session_one_active` | `23505` |
| Perfil solo con pertenencia real | `fk_supervisor_profile_membership` | `23503` |
| Hechos append-only inmutables | `trg_location_fix_append_only` | `P0001` |

El disparador respondio literalmente
`location_fix is append-only: UPDATE is not allowed`.

Las 10 donde **la consulta es la unica defensa** —y por tanto las que mas
importan— son: punto huerfano, punto y Missing a la vez, Missing sin registro de
aviso, total que no cuadra con sus tramos, tramo mas corto que la linea recta,
hueco en la secuencia de tramos, primer tramo que no sale de la salida, plan
original reescrito, cambio de plan fuera de transito, y coordenadas filtradas en
la traza de auditoria.

### Salud del esquema, medida

| Comprobacion | Esperado | Medido |
|---|---|---|
| Disparadores de proteccion activos | 14 (7 tablas x 2) | **14, todos `activo`** |
| Restricciones de invariante presentes | 13 | **13** |
| Indices unicos de correlacion | 8 | **8, todos unicos** |
| Head de Alembic | `0013_client_action_key`, 1 head | **`0013_client_action_key`, 1 fila** |

---

## 4. Hallazgos

### 4.1 De esquema

**`missing_location_event.attempts` es `jsonb`, no un entero.** `CONFIRMED`.
Guarda los registros de intento, no un contador. Lo descubri porque mi inyeccion
fallo con `42804`. No es un defecto —es el diseno— pero contradecia lo que yo
asumia, y cualquier consulta que la trate como numero fallara.

**`supervisor_profile` exige una pertenencia real.** `CONFIRMED`.
`fk_supervisor_profile_membership` referencia
`user_company(user_id, company_id)`: no puede existir un perfil para quien no
pertenece a la empresa. No estaba en el catalogo inicial; se anadio como `U-08`.

**`ck_trip_mileage_calculated_facts` es mas estricto de lo que yo cubria.**
`CONFIRMED`. Ademas de lo que comprobaba `K-02`, exige que un `calculated` **no**
lleve razon terminal y que un no-calculado **no** lleve fecha de calculo. Se
anadio `K-14` para la mitad que faltaba.

**`K-10` no puede devolver filas nunca.** `CONFIRMED` por `23502`. Todas las
columnas de provenance que comprueba son `NOT NULL`. Se conserva a proposito: deja
constancia ejecutable de que la garantia de §28 la sostiene el esquema. Si una
migracion futura aflojara esos `NOT NULL`, la consulta empezaria a devolver filas.

### 4.2 Errores propios, durante la ejecucion

Se reportan porque ocurrieron, aunque despues se corrigieran.

**Clasifique `T-06` como invariante dejandole un `:company_id`.** `CONFIRMED`.
Rompio `psql` con `ERROR: syntax error at or near ":"`. La correccion no fue
parametrizarla: un invariante debe barrer **todos** los tenants, asi que se quito
el filtro. El generador ahora lleva una asercion que impide que vuelva a pasar.

**Mi primera tanda de inyecciones dio 19 `RECHAZA` que no eran rechazos.**
`CONFIRMED`. Eran mis propios errores de script —`42P08` parametro ambiguo,
`42804` tipo, `22000` dato, `23503` FK no satisfecha— presentandose como si una
restriccion hubiera protegido el invariante. Los detecte leyendo los `sqlstate` en
vez de contar veredictos. Corregidos, 13 de esos 19 resultaron rechazos genuinos y
6 pasaron a `DETECTA`. **Si no lo hubiera revisado, el reporte habria atribuido a
la base garantias que no habian sido probadas.**

**Un bug de precedencia en `H-02`.** `CONFIRMED`. `WHERE NOT x AND a OR b` listaba
todos los disparadores `no_truncate` de la base en vez de los de las siete tablas.
Corregido con parentesis antes de la primera ejecucion.

---

## 5. Limites de lo entregado

Dicho explicitamente para que nadie lea el catalogo como mas de lo que es:

1. **El cero de esta corrida no dice nada sobre produccion.** El entorno donde se
   ejecuto tiene muy pocos datos: la mayoria de las 57 devuelve cero por falta de
   filas que examinar. Lo que hace util al cero es la verificacion por inyeccion.
2. **No sustituyen a los tests.** Comprueban el estado en reposo, no que la API
   rechace lo que debe rechazar. Un 403 que deberia ser 404 no deja rastro aqui.
3. **`L-14` y `K-04` tienen falsos positivos por diseno.** Un evento sin punto
   dentro de la ventana de recuperacion, o un pendiente con cita futura, son el
   mecanismo funcionando.
4. **La precision de campo no se audita desde SQL.** `L-09` describe la
   distribucion observada; no dice si los umbrales estan bien calibrados.

---

## 6. Estimacion de lo que falta

Baseline medido con `wc -l`, no recordado.

| Tarea | Estado | Volumen medido | Complejidad | Horas-agente |
|---|---|---|---|---|
| Catalogo, 89 consultas + generador | `COMPLETED` | 1.509 LoC de fuente -> 2.135 LoC generadas | backend/dominio | 8,5 |
| Arnes de inyeccion, 24 casos | `COMPLETED` | 380 LoC | integracion | 4,0 |
| Verificacion y correccion de 3 defectos | `COMPLETED` | 6 iteraciones | integracion | 2,0 |
| **Entregado** | | **2.515 LoC** | | **14,5** |

Pendiente, si CER lo quiere:

| Tarea | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| El arnes de inyeccion como test de la suite | `PENDING` | 380 LoC a portar | integracion | 3,0 |
| Correr la puerta contra un entorno con trafico | `PENDING` | — | operativo | 1,0 |
| Consultas de flujos aun no construidos (webhooks, plataforma) | `PENDING` | ~25 consultas, ~400 LoC | backend/dominio | 2,5 |
| **Subtotal** | | | | **6,5** |

Coeficientes estandar aplicados: backend/dominio **150-200 LoC/h** (se uso 175),
integracion **80-100 LoC/h** (se uso 90). Margen de riesgo **+10%**: trabajo
determinista, sin integraciones de terceros ni automatizacion de navegador.

**Total pendiente con margen: 7,2 horas-agente.**

Si se piden dias, el supuesto hay que declararlo: sobre una jornada-agente de 6
horas efectivas, 7,2 horas son **1,2 dias**. Las horas son el dato; los dias
dependen del supuesto.

---

## 7. Git

| | |
|---|---|
| Rama | `feature/sql-verification-catalogue` |
| Base | `dev` |
| Commits | 1 |
| Push | si |
| Arbol | limpio |
| MR | ver §9 |
| Fusionado | **no** — espera certificacion de CER |

---

## 8. Trabajo restante y accion operativa

**Accion operativa, si se quiere usar el catalogo:** correr
`route_invariantes.sql` contra el entorno compartido. Lo entregado aqui se
verifico **en local**; una corrida local no dice nada del entorno compartido.

**El arnes de inyeccion vive en el scratchpad de la sesion, no en el
repositorio.** Es lo que respalda la afirmacion central del documento, y sin el en
el repositorio esa afirmacion no se puede volver a verificar. No se anadio a la
suite porque el alcance pedido eran las consultas; queda como el siguiente paso
natural.

---

## 9. Siguiente paso

Portar el arnes de inyeccion a `tests/integration/` para que la puerta de
invariantes quede protegida por la propia suite. **No se ha empezado.**

MR abiertos que siguen esperando a CER: **!24** (odometro/OCR y vigencia de
asignacion, el mas antiguo sin resolver) y **!29** (cierre final de RTE06 en
Development).

RTE07 **no** empieza antes de la certificacion explicita de RTE06.
