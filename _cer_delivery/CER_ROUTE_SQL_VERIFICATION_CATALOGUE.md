# CER Route — Catalogo de consultas de verificacion

Consultas SQL para comprobar, **desde la base y sin pasar por la aplicacion**,
que el sistema cumple lo que dice cumplir. Cubre los flujos de RTE02 a RTE06.

Existe porque un test verde prueba que el codigo se comporta bien *en el camino
que el test recorre*. Estas consultas preguntan otra cosa: **que hay realmente en
la base**, incluido lo que entro por una importacion, un script o una version
anterior del codigo.

## Como se usa

Dos grupos, y la diferencia importa:

| Grupo | Resultado correcto | Que significa una fila |
|---|---|---|
| **Invariante** (`0`) | cero filas | **Un hallazgo.** Algo que no deberia poder pasar, paso |
| **Informe** | cualquiera | Estado para leer; no hay respuesta "mala" *a priori* |

### Elige el fichero segun con que lo vayas a correr

Hay cinco, y **no son alternativas de gusto**: los de `psql` no funcionan en un
cliente grafico y viceversa.

| Fichero | Para | Que devuelve |
|---|---|---|
| [`sql/route_invariantes_una_consulta.sql`](sql/route_invariantes_una_consulta.sql) | **Cualquier cliente.** Lo mas practico | UNA sentencia -> 57 filas, una por invariante, con su cuenta |
| [`sql/route_invariantes_cliente.sql`](sql/route_invariantes_cliente.sql) | DBeaver, DataGrip, pgAdmin | 57 sentencias sueltas |
| [`sql/route_informes_cliente.sql`](sql/route_informes_cliente.sql) | DBeaver, DataGrip, pgAdmin | 32 sentencias, con `:company_id` |
| [`sql/route_invariantes.sql`](sql/route_invariantes.sql) | **Solo `psql`** | 57 sentencias con etiquetas `\echo` |
| [`sql/route_informes.sql`](sql/route_informes.sql) | **Solo `psql`** | 32 sentencias, `-v company_id=N` |

**Si un cliente grafico da
`SQL Error [42601]: syntax error at or near "\"`**, es esto: `\echo` es un
meta-comando de `psql`, no SQL. Un cliente JDBC lo manda al servidor, que no sabe
que es. Usa los ficheros `_cliente` o el de una sola consulta.

### La forma recomendada

`route_invariantes_una_consulta.sql` se pega y se ejecuta, sin parametros ni
meta-comandos, y devuelve esto:

```
 id   | flujo                  | invariante                                  | filas
------+------------------------+---------------------------------------------+-------
 L-06 | Evidencia de ubicacion | Punto atado a una fila que no existe        |     1
 A-01 | Aislamiento de tenant  | Pertenencia con rol de otra empresa         |     0
 ...
```

Se lee de una vez: **`filas = 0` en las 57 es correcto; cualquier fila con
`filas > 0` es un hallazgo**, y sale arriba porque el orden es descendente. Se
verifico que senala: inyectando un punto huerfano, la puerta marco `L-06` en 1 y
**los otros 56 siguieron en 0** —detecta sin dar falsos positivos—.

Los ficheros de sentencias sueltas siguen siendo utiles cuando ya hay un hallazgo
y hace falta ver *que filas* son, no cuantas.

## Lo que respalda cada consulta de invariante

Una consulta de invariante que devuelve cero filas puede estar diciendo dos
cosas muy distintas, y confundirlas es peligroso:

- **RECHAZA** — la base **no deja escribir** la violacion. Se inyecto y una
  restriccion la rechazo. Cero filas es la consecuencia, no la prueba: la
  garantia es la restriccion, y la consulta solo confirma que sigue puesta.
- **DETECTA** — **nada impide** escribir la violacion. Se inyecto, se escribio, y
  la consulta la encontro. Aqui la consulta **es** la unica defensa, y por eso su
  correccion importa tanto.

Las 24 de la tabla siguiente se verificaron inyectando la violacion en una
transaccion que despues se revento. Ninguna resulto ciega.

| Consulta | Veredicto | Lo que rechazo la escritura | sqlstate |
|---|---|---|---|
| `D-02` Coordenadas filtradas en la traza de auditoria | DETECTA | *nada: la consulta es la defensa* | — |
| `H-01` Hechos append-only modificados despues de crearse | RECHAZA | `trg_location_fix_append_only` | `P0001` |
| `J-01` Mas de una jornada ACTIVA por supervisor | RECHAZA | `uq_work_session_one_active` | `23505` |
| `K-01` Mas de un kilometraje por viaje | RECHAZA | `uq_trip_mileage_trip` | `23505` |
| `K-02` Total publicado en un estado que no es `calculated` | RECHAZA | `ck_trip_mileage_calculated_facts` | `23514` |
| `K-05` Total que no cuadra con la suma de sus tramos | DETECTA | *nada: la consulta es la defensa* | — |
| `K-06` Tramo mas corto que la linea recta | DETECTA | *nada: la consulta es la defensa* | — |
| `K-07` Secuencia de tramos con hueco o duplicada | DETECTA | *nada: la consulta es la defensa* | — |
| `K-08` El primer tramo no sale de la salida, o el ultimo no llega | DETECTA | *nada: la consulta es la defensa* | — |
| `K-10` Provenance que sobrevive al purgado | RECHAZA | `NOT NULL trip_mileage_segment.from_latitude` | `23502` |
| `K-14` Calculado con razon terminal, o no calculado con fecha | RECHAZA | `ck_trip_mileage_calculated_facts` | `23514` |
| `L-01` Mas de un punto autoritativo por evento | RECHAZA | `uq_location_fix_event` | `23505` |
| `L-02` Nivel de evidencia fuera de los tres permitidos | RECHAZA | `ck_location_fix_evidence_level` | `23514` |
| `L-05` Pareja evento-sujeto imposible | RECHAZA | `ck_location_fix_event_subject` | `23514` |
| `L-06` Punto atado a una fila que no existe | DETECTA | *nada: la consulta es la defensa* | — |
| `L-08` Un evento con punto Y con Missing a la vez | DETECTA | *nada: la consulta es la defensa* | — |
| `L-11` Missing sin su registro de aviso | DETECTA | *nada: la consulta es la defensa* | — |
| `L-15` Motivo de Missing fuera del catalogo | RECHAZA | `ck_missing_location_reason` | `23514` |
| `T-01` Mas de un viaje vivo por jornada | RECHAZA | `uq_trip_one_non_terminal` | `23505` |
| `T-06` El plan original nunca se reescribe | DETECTA | *nada: la consulta es la defensa* | — |
| `T-08` Cambio de plan fuera de transito | DETECTA | *nada: la consulta es la defensa* | — |
| `U-08` Perfil de supervisor sin pertenencia a la empresa | RECHAZA | `fk_supervisor_profile_membership` | `23503` |
| `V-01` Asignaciones solapadas del mismo supervisor | RECHAZA | `ex_vehicle_assignment_no_overlap` | `23P01` |
| `V-02` Asignaciones de duracion cero | RECHAZA | `ck_vehicle_assignment_period` | `23514` |

## Inventario

**89 consultas** en 12 flujos: 57 de invariante y 32 de informe. Las 89 se ejecutaron contra PostgreSQL 16.4 con el esquema en `0013_client_action_key`: **0 errores de SQL**.

Los dos ficheros ejecutables se pasaron ademas por `psql` con `ON_ERROR_STOP=1`, que es como los correra quien valide:

| Fichero | exit | Consultas | Resultado |
|---|---|---|---|
| `route_invariantes.sql` | `0` | 57 | las 57 vacias: **ningun hallazgo en este entorno** |
| `route_informes.sql` | `0` | 32 | 20 vacias, 12 con filas |

Una advertencia sobre ese cero, porque es facil leerlo como mas de lo que es: **el entorno donde se ejecuto tiene muy pocos datos**, asi que la mayoria de las 57 devuelve cero por falta de filas que examinar, no porque se haya demostrado nada sobre datos de produccion. Lo que hace util al cero es la verificacion por inyeccion de la seccion anterior; correr la puerta contra un entorno con trafico real es un paso que **no** se ha hecho y queda como accion operativa.

| Flujo | Consultas | Invariante | Informe |
|---|---|---|---|
| Aislamiento de tenant | 8 | 8 | 0 |
| Usuarios y roles | 8 | 4 | 4 |
| Jornada de trabajo | 7 | 4 | 3 |
| Vigencia de vehiculo | 5 | 3 | 2 |
| Viajes | 8 | 7 | 1 |
| Odometro | 6 | 4 | 2 |
| Actividades | 5 | 3 | 2 |
| Evidencia de ubicacion | 15 | 11 | 4 |
| Kilometraje | 14 | 10 | 4 |
| Correlacion offline | 3 | 1 | 2 |
| Integridad historica | 5 | 1 | 4 |
| Auditoria | 5 | 1 | 4 |

---

## Aislamiento de tenant
### A-01 — Pertenencia con rol de otra empresa

**Invariante** — debe devolver cero filas

Un rol solo puede concederse dentro de su propia empresa. La FK compuesta lo impide, y esto lo comprueba desde fuera del ORM.

```sql
SELECT uc.id AS user_company_id, uc.company_id, uc.role_id, r.company_id AS role_company_id
FROM user_company uc
JOIN role r ON r.id = uc.role_id
WHERE r.company_id <> uc.company_id
```
### A-02 — Jornada cuyo vehiculo es de otra empresa

**Invariante** — debe devolver cero filas

El snapshot de vehiculo de una jornada no puede apuntar a un vehiculo ajeno.

```sql
SELECT ws.id AS work_session_id, ws.company_id, ws.vehicle_id, v.company_id AS vehicle_company_id
FROM work_session ws
JOIN vehicle v ON v.id = ws.vehicle_id
WHERE v.company_id <> ws.company_id
```
### A-03 — Viaje colgado de la jornada de otra empresa

**Invariante** — debe devolver cero filas

La FK compuesta lo hace imposible; se verifica en datos.

```sql
SELECT t.id AS trip_id, t.company_id, ws.company_id AS session_company_id
FROM trip t
JOIN work_session ws ON ws.id = t.work_session_id
WHERE ws.company_id <> t.company_id
```
### A-04 — Punto de ubicacion en jornada de otra empresa

**Invariante** — debe devolver cero filas

Es el invariante 5 del soak, comprobado directamente.

```sql
SELECT f.id AS location_fix_id, f.company_id, ws.company_id AS session_company_id
FROM location_fix f
JOIN work_session ws ON ws.id = f.work_session_id
WHERE ws.company_id <> f.company_id
```
### A-05 — Kilometraje cuyo viaje es de otra empresa

**Invariante** — debe devolver cero filas

Un hecho de kilometraje no puede describir el viaje de otro tenant.

```sql
SELECT m.id AS trip_mileage_id, m.company_id, t.company_id AS trip_company_id
FROM trip_mileage m
JOIN trip t ON t.id = m.trip_id
WHERE t.company_id <> m.company_id
```
### A-06 — Aviso de Missing cuyo hecho es de otra empresa

**Invariante** — debe devolver cero filas

La FK compuesta lo impide; se comprueba.

```sql
SELECT n.id AS notification_id, n.company_id, e.company_id AS event_company_id
FROM missing_location_notification n
JOIN missing_location_event e ON e.id = n.missing_location_event_id
WHERE e.company_id <> n.company_id
```
### A-07 — Tramo cuyo kilometraje padre es de otra empresa

**Invariante** — debe devolver cero filas

La provenance no puede cruzar tenants.

```sql
SELECT s.id AS segment_id, s.company_id, m.company_id AS parent_company_id
FROM trip_mileage_segment s
JOIN trip_mileage m ON m.id = s.trip_mileage_id
WHERE m.company_id <> s.company_id
```
### A-08 — Valor de lista de otra empresa usado en un viaje

**Invariante** — debe devolver cero filas

El contexto de un viaje no puede referenciar el catalogo de otra empresa.

```sql
SELECT t.id AS trip_id, t.company_id, t.current_standard_value_id, sv.company_id AS value_company_id
FROM trip t
JOIN standard_value sv ON sv.id = t.current_standard_value_id
WHERE sv.company_id <> t.company_id
```

---

## Usuarios y roles
### U-01 — Pertenencias duplicadas de una persona en una empresa

**Invariante** — debe devolver cero filas

`uq_user_company_user_company` es COMPLETO, no parcial: una persona tiene como maximo un rol por empresa, incluso si fue retirada y readmitida. Readmitir levanta la lapida de la fila existente, no crea otra (RTE02-A03).

```sql
SELECT user_id, company_id, count(*) AS cuantas
FROM user_company
GROUP BY user_id, company_id
HAVING count(*) > 1
```
### U-02 — Acceso retirado que sigue activo

**Invariante** — debe devolver cero filas

`deleted_at` cierra el acceso. Una fila con lapida y activa a la vez seria un estado que las dos puertas de autorizacion interpretarian distinto.

```sql
SELECT id, user_id, company_id, is_active, deleted_at
FROM user_company
WHERE deleted_at IS NOT NULL AND is_active IS TRUE
```
### U-03 — Rol de CER Route concedido a alguien sin perfil, y viceversa

**Informe** — se lee, no se aprueba

INFORME. El perfil de supervisor es OPCIONAL: sin el, la jornada arranca con `vehicle_id = NULL` y el odometro en NOT_REQUIRED. Un `supervisor` sin perfil es valido; lo que esta lista permite es ver quien tiene vehiculo asignable.

```sql
SELECT u.username, r.name AS rol, sp.id AS supervisor_profile_id
FROM user_company uc
JOIN role r ON r.id = uc.role_id
JOIN "user" u ON u.id = uc.user_id
LEFT JOIN supervisor_profile sp
  ON sp.user_id = uc.user_id AND sp.company_id = uc.company_id
   AND sp.deleted_at IS NULL
WHERE uc.company_id = :company_id
  AND r.name IN ('supervisor', 'route_admin')
ORDER BY r.name, u.username
```
### U-04 — Superusuarios de plataforma

**Informe** — se lee, no se aprueba

INFORME, y de los importantes: `is_superuser` es privilegio de PLATAFORMA y hace retorno inmediato en `require_permissions`. Esta lista deberia ser corta y conocida. Una cuenta inesperada aqui es un hallazgo de seguridad.

```sql
SELECT id, username, email, is_active, last_login
FROM "user"
WHERE is_superuser IS TRUE
ORDER BY id
```
### U-05 — Roles sin ninguna capacidad concedida

**Informe** — se lee, no se aprueba

Un rol activo sin capacidades concede autoridad nominal sobre nada. No es necesariamente un defecto, pero conviene saberlo.

```sql
SELECT r.id, r.name, r.category, count(rp.id) AS capacidades
FROM role r
LEFT JOIN role_permission rp ON rp.role_id = r.id AND rp.is_active IS TRUE
WHERE r.company_id = :company_id AND r.is_active IS TRUE
GROUP BY r.id, r.name, r.category
HAVING count(rp.id) = 0
```
### U-06 — Solicitudes de cambio de capacidades pendientes

**Informe** — se lee, no se aprueba

INFORME. El flujo es maker-checker: quien pide no aprueba. Una solicitud pendiente mucho tiempo bloquea el cambio de ese rol (solo una por rol).

```sql
SELECT rq.id, r.name AS rol, rq.status, rq.requested_by_user_id,
       rq.reviewed_by_user_id, rq.created_at
FROM role_permission_change_request rq
JOIN role r ON r.id = rq.role_id
WHERE rq.company_id = :company_id AND rq.status = 'pending'
ORDER BY rq.created_at
```
### U-07 — Aprobaciones donde quien pidio tambien reviso

**Invariante** — debe devolver cero filas

Quien solicita no puede aprobar lo suyo. Es la regla 2 del flujo de aprobacion y aqui se comprueba sobre los datos.

```sql
SELECT id, role_id, requested_by_user_id, reviewed_by_user_id, status
FROM role_permission_change_request
WHERE reviewed_by_user_id IS NOT NULL
  AND reviewed_by_user_id = requested_by_user_id
```
### U-08 — Perfil de supervisor sin pertenencia a la empresa

**Invariante** — debe devolver cero filas

`fk_supervisor_profile_membership` referencia `user_company(user_id, company_id)`: un perfil solo puede existir para quien PERTENECE a la empresa. Sin eso, retirar a alguien dejaria un perfil vivo con vehiculo asignable.  
*Verificado inyectando la violacion:* la base la **rechazo** con `23503` por `fk_supervisor_profile_membership`. La garantia es esa restriccion; la consulta confirma que sigue puesta.

```sql
SELECT sp.id AS supervisor_profile_id, sp.company_id, sp.user_id
FROM supervisor_profile sp
WHERE NOT EXISTS (
    SELECT 1 FROM user_company uc
    WHERE uc.user_id = sp.user_id AND uc.company_id = sp.company_id
)
```

---

## Jornada de trabajo
### J-01 — Mas de una jornada ACTIVA por supervisor

**Invariante** — debe devolver cero filas

El invariante de UNA jornada activa. Lo protege un indice unico parcial; esto lo comprueba desde los datos.  
*Verificado inyectando la violacion:* la base la **rechazo** con `23505` por `uq_work_session_one_active`. La garantia es esa restriccion; la consulta confirma que sigue puesta.

```sql
SELECT company_id, user_id, count(*) AS activas
FROM work_session
WHERE status = 'active'
GROUP BY company_id, user_id
HAVING count(*) > 1
```
### J-02 — Jornada terminada antes de empezar

**Invariante** — debe devolver cero filas

Un CHECK lo impide. Si apareciera, la hora de ocurrencia se habria escrito mal y toda duracion derivada seria falsa.

```sql
SELECT id, company_id, user_id, started_at, ended_at
FROM work_session
WHERE ended_at IS NOT NULL AND ended_at < started_at
```
### J-03 — Jornada ENDED sin hora de cierre

**Invariante** — debe devolver cero filas

Un estado terminal sin su hecho terminal. Es el mismo patron que RTE05 cierra para las actividades.

```sql
SELECT id, company_id, status, started_at, ended_at
FROM work_session
WHERE status = 'ended' AND ended_at IS NULL
```
### J-04 — Ocurrencia posterior a la recepcion

**Invariante** — debe devolver cero filas

Causalidad: una accion no puede ocurrir despues de recibirse. El margen de 5 minutos es la deriva de reloj que `_resolve_occurrence` tolera.

```sql
SELECT id, company_id, started_at, started_received_at, started_at_source
FROM work_session
WHERE started_received_at IS NOT NULL
  AND started_at > started_received_at + interval '5 minutes'
```
### J-05 — Origen de la hora de inicio, distribucion

**Informe** — se lee, no se aprueba

INFORME. `device` significa que se acepto el reloj del dispositivo (accion encolada sin red); `server_receipt` que se uso el del servidor. El retraso medio dice cuanto se trabaja sin cobertura.

```sql
SELECT started_at_source, count(*) AS cuantas,
       round(avg(EXTRACT(EPOCH FROM (started_received_at - started_at)))::numeric, 1) AS retraso_medio_s
FROM work_session
WHERE company_id = :company_id
GROUP BY started_at_source
ORDER BY cuantas DESC
```
### J-06 — Jornadas sin vehiculo aplicable

**Informe** — se lee, no se aprueba

INFORME, y es un caso VALIDO: sin asignacion vigente la jornada arranca igual y el odometro queda NOT_REQUIRED (RTE06 §8.2). Que haya filas aqui no es un defecto.

```sql
SELECT id, user_id, session_date, vehicle_id, mpg_snapshot
FROM work_session
WHERE company_id = :company_id AND vehicle_id IS NULL
ORDER BY session_date DESC
```
### J-07 — Snapshot de MPG sin vehiculo, o al contrario

**Informe** — se lee, no se aprueba

El snapshot es del vehiculo: uno sin el otro describe un hecho a medias. Con vehiculo y sin MPG puede ser legitimo si el vehiculo no tenia MPG, asi que revisar antes de tratarlo como defecto.

```sql
SELECT id, company_id, vehicle_id, mpg_snapshot
FROM work_session
WHERE (vehicle_id IS NULL AND mpg_snapshot IS NOT NULL)
   OR (vehicle_id IS NOT NULL AND mpg_snapshot IS NULL)
```

---

## Vigencia de vehiculo
### V-01 — Asignaciones solapadas del mismo supervisor

**Invariante** — debe devolver cero filas

Es el invariante E5 de RTE06-CP0. Lo garantiza `ex_vehicle_assignment_no_overlap`; esta consulta usa el MISMO operador de rango, asi que comprueba lo mismo que la restriccion desde fuera.  
*Verificado inyectando la violacion:* la base la **rechazo** con `23P01` por `ex_vehicle_assignment_no_overlap`. La garantia es esa restriccion; la consulta confirma que sigue puesta.

```sql
SELECT a.id AS a_id, b.id AS b_id, a.supervisor_profile_id,
       a.effective_from AS a_desde, a.effective_to AS a_hasta,
       b.effective_from AS b_desde, b.effective_to AS b_hasta
FROM vehicle_assignment a
JOIN vehicle_assignment b
  ON b.company_id = a.company_id
 AND b.supervisor_profile_id = a.supervisor_profile_id
 AND b.id > a.id
WHERE tstzrange(a.effective_from, a.effective_to, '[)')
   && tstzrange(b.effective_from, b.effective_to, '[)')
```
### V-02 — Asignaciones de duracion cero

**Invariante** — debe devolver cero filas

Una fila que afirma 'asignado desde t hasta t' no afirma ningun hecho, y un rango vacio NO solapa, asi que `EXCLUDE` no lo ve. Lo dejaba el camino concurrente antes de la migracion 0012. Si hay filas, esa empresa paso por la carrera ANTES de desplegar 0012.  
*Verificado inyectando la violacion:* la base la **rechazo** con `23514` por `ck_vehicle_assignment_period`. La garantia es esa restriccion; la consulta confirma que sigue puesta.

```sql
SELECT id, company_id, supervisor_profile_id, vehicle_id, effective_from, effective_to
FROM vehicle_assignment
WHERE effective_to IS NOT NULL AND effective_to = effective_from
```
### V-03 — Mas de una asignacion abierta por supervisor

**Invariante** — debe devolver cero filas

El indice unico parcial `uq_vehicle_assignment_current`. Mas estrecho que el EXCLUDE y sigue siendo util.

```sql
SELECT company_id, supervisor_profile_id, count(*) AS abiertas
FROM vehicle_assignment
WHERE effective_to IS NULL
GROUP BY company_id, supervisor_profile_id
HAVING count(*) > 1
```
### V-04 — El vehiculo que una jornada deberia haber resuelto

**Informe** — se lee, no se aprueba

LA CONSULTA CLAVE DE CP0. Recalcula, para cada jornada, que asignacion estaba vigente en su HORA DE OCURRENCIA y lo compara con el snapshot que se guardo. `discrepa = true` es un hallazgo: significa que el snapshot no uso la hora de ocurrencia, o que alguien reasigno hacia atras.

```sql
SELECT ws.id AS work_session_id, ws.started_at, ws.vehicle_id AS vehiculo_en_snapshot,
       va.vehicle_id AS vehiculo_vigente_entonces,
       (ws.vehicle_id IS DISTINCT FROM va.vehicle_id) AS discrepa
FROM work_session ws
JOIN supervisor_profile sp
  ON sp.user_id = ws.user_id AND sp.company_id = ws.company_id
LEFT JOIN vehicle_assignment va
  ON va.company_id = ws.company_id
 AND va.supervisor_profile_id = sp.id
 AND va.effective_from <= ws.started_at
 AND (va.effective_to IS NULL OR va.effective_to > ws.started_at)
WHERE ws.company_id = :company_id
ORDER BY ws.started_at DESC
```
### V-05 — Historial de asignaciones de un supervisor

**Informe** — se lee, no se aprueba

INFORME. El historial completo, para leer que se condujo y cuando. Dos filas consecutivas deben TOCARSE sin solapar: `effective_to` de una igual a `effective_from` de la siguiente.

```sql
SELECT va.supervisor_profile_id, u.username, v.unit AS vehiculo,
       va.effective_from, va.effective_to,
       CASE WHEN va.effective_to IS NULL THEN 'abierta' ELSE 'cerrada' END AS estado
FROM vehicle_assignment va
JOIN supervisor_profile sp ON sp.id = va.supervisor_profile_id
JOIN "user" u ON u.id = sp.user_id
JOIN vehicle v ON v.id = va.vehicle_id
WHERE va.company_id = :company_id
ORDER BY u.username, va.effective_from
```

---

## Viajes
### T-01 — Mas de un viaje vivo por jornada

**Invariante** — debe devolver cero filas

Un indice unico parcial lo impide. Dos viajes vivos harian que 'el viaje actual' tuviera dos respuestas.  
*Verificado inyectando la violacion:* la base la **rechazo** con `23505` por `uq_trip_one_non_terminal`. La garantia es esa restriccion; la consulta confirma que sigue puesta.

```sql
SELECT company_id, work_session_id, count(*) AS vivos
FROM trip
WHERE status NOT IN ('closed', 'interrupted')
GROUP BY company_id, work_session_id
HAVING count(*) > 1
```
### T-02 — Secuencia de viaje duplicada o con huecos

**Invariante** — debe devolver cero filas

La secuencia ordena los viajes del dia. Duplicarla hace ambiguo el orden.

```sql
SELECT work_session_id, sequence, count(*) AS cuantos
FROM trip
GROUP BY work_session_id, sequence
HAVING count(*) > 1
```
### T-03 — Viaje ARRIVED o CLOSED sin hora de llegada

**Invariante** — debe devolver cero filas

Llegar sin hora de llegada deja el waypoint final sin ancla temporal, y el kilometraje lo necesita para ordenar.

```sql
SELECT id, company_id, status, started_at, arrived_at
FROM trip
WHERE status IN ('arrived', 'closed') AND arrived_at IS NULL
```
### T-04 — Llegada anterior a la salida

**Invariante** — debe devolver cero filas

Imposible en el dominio. Si aparece, una hora de ocurrencia se escribio mal.

```sql
SELECT id, company_id, started_at, arrived_at
FROM trip
WHERE arrived_at IS NOT NULL AND started_at IS NOT NULL AND arrived_at < started_at
```
### T-05 — Viaje IN_TRANSIT sin hora de salida

**Invariante** — debe devolver cero filas

En transito sin haber salido. El waypoint de salida no tendria ancla.

```sql
SELECT id, company_id, status, started_at
FROM trip
WHERE status = 'in_transit' AND started_at IS NULL
```
### T-06 — El plan original nunca se reescribe

**Invariante** — debe devolver cero filas

El PRIMER cambio de plan debe partir del proposito ORIGINAL. Si no coincide, `original_purpose` se reescribio en algun momento, y RTE04 lo declara inmutable.  
*Verificado inyectando la violacion:* nada impide escribirla y la consulta la **encontro**. Aqui la consulta es la unica defensa.

```sql
SELECT t.company_id, t.id AS trip_id, t.original_purpose, t.current_purpose,
       count(c.id) AS cambios,
       min(c.from_purpose) AS primer_from
FROM trip t
LEFT JOIN trip_purpose_change c ON c.trip_id = t.id AND c.company_id = t.company_id
GROUP BY t.company_id, t.id, t.original_purpose, t.current_purpose
HAVING count(c.id) > 0 AND min(c.from_purpose) <> t.original_purpose
```
### T-07 — Cadena de cambios de plan con un salto

**Informe** — se lee, no se aprueba

INFORME para leer a ojo: el `from_purpose` de cada cambio debe ser igual al `to_purpose` del anterior. Un salto significa que se perdio un cambio intermedio, y el kilometraje habria perdido un waypoint.

```sql
SELECT c.trip_id, c.id, c.changed_at, c.from_purpose, c.to_purpose,
       lag(c.to_purpose) OVER (PARTITION BY c.trip_id ORDER BY c.changed_at, c.id) AS to_anterior
FROM trip_purpose_change c
WHERE c.company_id = :company_id
ORDER BY c.trip_id, c.changed_at, c.id
```
### T-08 — Cambio de plan fuera de transito

**Invariante** — debe devolver cero filas

`Change Plan` solo esta disponible EN TRANSITO. Un cambio con hora fuera del intervalo salida-llegada contradice esa regla certificada de RTE04.  
*Verificado inyectando la violacion:* nada impide escribirla y la consulta la **encontro**. Aqui la consulta es la unica defensa.

```sql
SELECT c.id, c.trip_id, c.changed_at, t.status, t.started_at, t.arrived_at
FROM trip_purpose_change c
JOIN trip t ON t.id = c.trip_id AND t.company_id = c.company_id
WHERE t.started_at IS NOT NULL
  AND (c.changed_at < t.started_at
       OR (t.arrived_at IS NOT NULL AND c.changed_at > t.arrived_at))
```

---

## Odometro
### O-01 — Lectura confirmada sin quien la confirmo

**Invariante** — debe devolver cero filas

La lectura oficial es la CONFIRMADA POR EL SUPERVISOR. Sin quien ni cuando, deja de ser evidencia atribuible.

```sql
SELECT id, company_id, evidence_type, status, confirmed_reading, confirmed_by, confirmed_at
FROM odometer_evidence
WHERE confirmed_reading IS NOT NULL AND (confirmed_by IS NULL OR confirmed_at IS NULL)
```
### O-02 — Mas de una evidencia del mismo tipo por jornada

**Invariante** — debe devolver cero filas

Una lectura de inicio y una de fin por jornada. Dos harian ambigua la distancia del dia.

```sql
SELECT company_id, work_session_id, evidence_type, count(*) AS cuantas
FROM odometer_evidence
GROUP BY company_id, work_session_id, evidence_type
HAVING count(*) > 1
```
### O-03 — Lectura de fin menor que la de inicio

**Invariante** — debe devolver cero filas

Un odometro no cuenta hacia atras. Si aparece, hay un error de captura o un cambio de vehiculo no registrado.

```sql
SELECT i.work_session_id, i.confirmed_reading AS inicio, f.confirmed_reading AS fin
FROM odometer_evidence i
JOIN odometer_evidence f
  ON f.work_session_id = i.work_session_id AND f.company_id = i.company_id
WHERE i.evidence_type = 'start' AND f.evidence_type = 'end'
  AND i.confirmed_reading IS NOT NULL AND f.confirmed_reading IS NOT NULL
  AND f.confirmed_reading < i.confirmed_reading
```
### O-04 — Excepciones de odometro y su estado

**Informe** — se lee, no se aprueba

INFORME. El camino sin foto es la excepcion controlada por el administrador. Una aprobada y nunca consumida es autoridad concedida y no usada.

```sql
SELECT r.id, r.work_session_id, r.evidence_type, r.status, r.reason,
       r.requested_by, r.requested_at, r.decided_by, r.decided_at, r.consumed_at
FROM odometer_exception_request r
WHERE r.company_id = :company_id
ORDER BY r.requested_at DESC
```
### O-05 — Excepcion decidida sin quien la decidio

**Invariante** — debe devolver cero filas

Una decision sin firma no es auditable, y esta es la que permite saltarse la foto.

```sql
SELECT id, work_session_id, status, decided_by, decided_at
FROM odometer_exception_request
WHERE status IN ('approved', 'rejected')
  AND (decided_by IS NULL OR decided_at IS NULL)
```
### O-06 — Estado de las lecturas por jornada

**Informe** — se lee, no se aprueba

INFORME. `photo_confirmed` es el camino normal. Mucho `no_photo` significa que la excepcion se esta usando como norma.

```sql
SELECT e.evidence_type, e.status, e.evidence_method, count(*) AS cuantas
FROM odometer_evidence e
WHERE e.company_id = :company_id
GROUP BY e.evidence_type, e.status, e.evidence_method
ORDER BY e.evidence_type, cuantas DESC
```

---

## Actividades
### C-01 — Mas de un bloque de ejecucion por viaje

**Invariante** — debe devolver cero filas

PD-01: UN bloque por parada. Varias actividades son ETIQUETAS del mismo bloque, no bloques distintos. Lo impide `uq_activity_execution_trip`.

```sql
SELECT company_id, trip_id, count(*) AS bloques
FROM activity_execution
GROUP BY company_id, trip_id
HAVING count(*) > 1
```
### C-02 — Bloque terminal sin hora de fin o sin resultado

**Invariante** — debe devolver cero filas

Terminar exige hora Y resultado. Un bloque terminal sin resultado seria el hecho fabricado que RTE05 prohibe, y `ck_activity_execution_terminal_facts` lo impide.

```sql
SELECT id, company_id, trip_id, status, terminal_action, ended_at,
       outcome_standard_value_id, outcome_label
FROM activity_execution
WHERE status IN ('completed', 'left')
  AND (ended_at IS NULL OR (outcome_standard_value_id IS NULL AND outcome_label IS NULL))
```
### C-03 — Bloque sin ninguna actividad etiquetada

**Informe** — se lee, no se aprueba

INFORME. Un bloque sin etiquetas puede ser valido —hay paradas sin actividad de lista— pero conviene verlo.

```sql
SELECT ae.id, ae.company_id, ae.trip_id, ae.status
FROM activity_execution ae
LEFT JOIN activity_execution_activity a ON a.activity_execution_id = ae.id
WHERE ae.company_id = :company_id
GROUP BY ae.id, ae.company_id, ae.trip_id, ae.status
HAVING count(a.id) = 0
```
### C-04 — La etiqueta guardada frente al valor de lista actual

**Informe** — se lee, no se aprueba

INFORME, y es ESPERADO: la etiqueta se copia al ejecutar para que el historico siga legible si el administrador renombra el valor. Filas aqui demuestran que la copia funciona, no que algo falle.

```sql
SELECT a.id, a.label AS etiqueta_guardada, sv.label AS etiqueta_actual,
       sv.deleted_at, sv.is_active
FROM activity_execution_activity a
JOIN standard_value sv ON sv.id = a.standard_value_id
WHERE a.company_id = :company_id AND a.label <> sv.label
```
### C-05 — Bloque cuyo viaje no habia llegado

**Invariante** — debe devolver cero filas

El trabajo de la parada empieza DESPUES de llegar. Antes seria un bloque sobre un viaje que no habia terminado de viajar.

```sql
SELECT ae.id, ae.trip_id, ae.started_at, t.status, t.arrived_at
FROM activity_execution ae
JOIN trip t ON t.id = ae.trip_id AND t.company_id = ae.company_id
WHERE t.arrived_at IS NULL OR ae.started_at < t.arrived_at
```

---

## Evidencia de ubicacion
### L-15 — Motivo de Missing fuera del catalogo

**Invariante** — debe devolver cero filas

Los seis motivos describen HECHOS OBSERVABLES. Un septimo valor abriria la puerta a registrar una causa que la plataforma no puede demostrar, que es justo lo que §11 prohibe.  
*Verificado inyectando la violacion:* la base la **rechazo** con `23514` por `ck_missing_location_reason`. La garantia es esa restriccion; la consulta confirma que sigue puesta.

```sql
SELECT id, company_id, event_kind, reason_code
FROM missing_location_event
WHERE reason_code NOT IN (
    'permission_denied', 'position_unavailable', 'acquisition_timeout',
    'cached_rejected', 'recovery_window_exhausted', 'no_client_report'
)
```
### L-01 — Mas de un punto autoritativo por evento

**Invariante** — debe devolver cero filas

LA correlacion de RTE06 §14. Un evento del ciclo de vida tiene como maximo un punto. Lo garantiza `uq_location_fix_event`, y es lo que hace idempotente el reenvio de la cola offline.  
*Verificado inyectando la violacion:* la base la **rechazo** con `23505` por `uq_location_fix_event`. La garantia es esa restriccion; la consulta confirma que sigue puesta.

```sql
SELECT company_id, event_kind, subject_kind, subject_id, count(*) AS puntos
FROM location_fix
GROUP BY company_id, event_kind, subject_kind, subject_id
HAVING count(*) > 1
```
### L-02 — Nivel de evidencia fuera de los tres permitidos

**Invariante** — debe devolver cero filas

EXACTAMENTE tres niveles. `missing` NO es uno: la ausencia vive en `missing_location_event`. Un cuarto valor obligaria a cada consulta de waypoints a acordarse de excluirlo.  
*Verificado inyectando la violacion:* la base la **rechazo** con `23514` por `ck_location_fix_evidence_level`. La garantia es esa restriccion; la consulta confirma que sigue puesta.

```sql
SELECT id, company_id, event_kind, evidence_level
FROM location_fix
WHERE evidence_level NOT IN ('fresh', 'degraded_cached', 'recovered')
```
### L-03 — Punto cacheado sin edad, o fresco con ella

**Invariante** — debe devolver cero filas

Un `fresh` con edad es una contradiccion; un `degraded_cached` sin ella no se puede auditar —RTE06 §28 exige saber de cuando era la coordenada usada.

```sql
SELECT id, company_id, event_kind, evidence_level, source_age_seconds
FROM location_fix
WHERE (evidence_level = 'degraded_cached' AND source_age_seconds IS NULL)
   OR (evidence_level <> 'degraded_cached' AND source_age_seconds IS NOT NULL)
```
### L-04 — Coordenadas fuera de rango

**Invariante** — debe devolver cero filas

Validado en el schema Y en la tabla. La restriccion protege el camino que no pasa por la API: un script, una importacion.

```sql
SELECT id, company_id, latitude, longitude
FROM location_fix
WHERE latitude < -90 OR latitude > 90 OR longitude < -180 OR longitude > 180
```
### L-05 — Pareja evento-sujeto imposible

**Invariante** — debe devolver cero filas

Un `change_plan` colgado de una jornada seria una correlacion imposible de reconstruir. La pareja se deriva de un diccionario y se comprueba en la base.  
*Verificado inyectando la violacion:* la base la **rechazo** con `23514` por `ck_location_fix_event_subject`. La garantia es esa restriccion; la consulta confirma que sigue puesta.

```sql
SELECT id, company_id, event_kind, subject_kind
FROM location_fix
WHERE NOT (
     (event_kind IN ('start_work','end_work') AND subject_kind = 'work_session')
  OR (event_kind IN ('start_trip','arrived')  AND subject_kind = 'trip')
  OR (event_kind = 'change_plan'              AND subject_kind = 'trip_purpose_change')
  OR (event_kind IN ('activity_complete','activity_leave') AND subject_kind = 'activity_execution')
)
```
### L-06 — Punto atado a una fila que no existe

**Invariante** — debe devolver cero filas

Invariante 2 del soak. Un punto huerfano significa que la correlacion se ato a algo que no esta, y ninguna FK lo impide porque `subject_id` es polimorfico.  
*Verificado inyectando la violacion:* nada impide escribirla y la consulta la **encontro**. Aqui la consulta es la unica defensa.

```sql
SELECT f.id, f.event_kind, f.subject_kind, f.subject_id
FROM location_fix f
WHERE (f.subject_kind = 'trip' AND NOT EXISTS (
          SELECT 1 FROM trip t WHERE t.id = f.subject_id AND t.company_id = f.company_id))
   OR (f.subject_kind = 'trip_purpose_change' AND NOT EXISTS (
          SELECT 1 FROM trip_purpose_change c WHERE c.id = f.subject_id AND c.company_id = f.company_id))
   OR (f.subject_kind = 'work_session' AND NOT EXISTS (
          SELECT 1 FROM work_session w WHERE w.id = f.subject_id AND w.company_id = f.company_id))
   OR (f.subject_kind = 'activity_execution' AND NOT EXISTS (
          SELECT 1 FROM activity_execution a WHERE a.id = f.subject_id AND a.company_id = f.company_id))
```
### L-07 — Captura posterior a la recepcion

**Invariante** — debe devolver cero filas

Una medicion no puede ocurrir despues de recibirse. Margen de 5 minutos por deriva de reloj del dispositivo.

```sql
SELECT id, company_id, event_kind, device_captured_at, server_received_at
FROM location_fix
WHERE device_captured_at > server_received_at + interval '5 minutes'
```
### L-08 — Un evento con punto Y con Missing a la vez

**Invariante** — debe devolver cero filas

El punto MANDA sobre el Missing. Los dos a la vez obligarian al motor de kilometraje a decidir cual cree, y esa decision no debe existir.  
*Verificado inyectando la violacion:* nada impide escribirla y la consulta la **encontro**. Aqui la consulta es la unica defensa.

```sql
SELECT f.company_id, f.event_kind, f.subject_kind, f.subject_id
FROM location_fix f
JOIN missing_location_event m
  ON m.company_id = f.company_id AND m.event_kind = f.event_kind
 AND m.subject_kind = f.subject_kind AND m.subject_id = f.subject_id
```
### L-09 — Distribucion de niveles de evidencia

**Informe** — se lee, no se aprueba

INFORME. ES LA CONSULTA DEL ITEM F de la validacion de campo. `missing` NO aparece aqui a proposito: no es un nivel, y sumarlo en el mismo porcentaje contradiria §11. Se cuenta aparte en L-10.

```sql
SELECT evidence_level, count(*) AS cuantos,
       round(100.0 * count(*) / NULLIF(sum(count(*)) OVER (), 0), 1) AS pct,
       round(avg(accuracy_m)::numeric, 1) AS precision_media_m,
       round(avg(source_age_seconds)::numeric, 1) AS edad_media_s
FROM location_fix
WHERE company_id = :company_id
GROUP BY evidence_level
ORDER BY cuantos DESC
```
### L-10 — Ubicaciones perdidas por motivo

**Informe** — se lee, no se aprueba

INFORME. Los motivos describen HECHOS OBSERVABLES, nunca causas que la plataforma no pueda demostrar. Mucho `permission_denied` es un problema de adopcion; mucho `no_client_report` significa que el barrido del servidor esta cerrando eventos que el cliente abandono.

```sql
SELECT reason_code, permission_state, count(*) AS cuantas
FROM missing_location_event
WHERE company_id = :company_id
GROUP BY reason_code, permission_state
ORDER BY cuantas DESC
```
### L-11 — Missing sin su registro de aviso

**Invariante** — debe devolver cero filas

El hecho y su registro de entrega nacen en la MISMA transaccion. Un hecho sin fila de aviso quedaria invisible para quien entregue los avisos.  
*Verificado inyectando la violacion:* nada impide escribirla y la consulta la **encontro**. Aqui la consulta es la unica defensa.

```sql
SELECT e.id, e.company_id, e.event_kind, e.subject_id, e.occurred_at
FROM missing_location_event e
WHERE NOT EXISTS (
    SELECT 1 FROM missing_location_notification n
    WHERE n.missing_location_event_id = e.id AND n.company_id = e.company_id
)
```
### L-12 — Aviso entregado sin fecha de entrega

**Invariante** — debe devolver cero filas

Un aviso que dice 'entregado' sin decir cuando hace inauditable la entrega, que es lo unico para lo que esa tabla existe.

```sql
SELECT id, company_id, missing_location_event_id, channel, status, delivered_at
FROM missing_location_notification
WHERE (status = 'notified' AND delivered_at IS NULL)
   OR (status <> 'notified' AND delivered_at IS NOT NULL)
```
### L-13 — Avisos pendientes de entregar

**Informe** — se lee, no se aprueba

INFORME. RTE06 PERSISTE el estado y expone el contrato; NO entrega el aviso. Todo pendiente es lo esperado hasta que exista el componente de entrega.

```sql
SELECT n.channel, n.status, count(*) AS cuantos,
       min(e.occurred_at) AS mas_antiguo
FROM missing_location_notification n
JOIN missing_location_event e ON e.id = n.missing_location_event_id
WHERE n.company_id = :company_id
GROUP BY n.channel, n.status
ORDER BY n.channel, cuantos DESC
```
### L-14 — Eventos ocurridos sin punto y sin Missing

**Informe** — se lee, no se aprueba

INFORME, y la mas util para operar. Estos eventos estan en LIMBO: ni punto ni Missing. Es normal DENTRO de la ventana de recuperacion (180s + margen). Uno con antiguedad de horas significa que el barrido del servidor no esta corriendo.

```sql
SELECT e.company_id, e.event_kind, e.subject_id, e.occurred_at,
       EXTRACT(EPOCH FROM (now() - e.occurred_at))::int AS antiguedad_s
FROM (
    SELECT company_id, 'start_trip' AS event_kind, id AS subject_id, started_at AS occurred_at
    FROM trip WHERE started_at IS NOT NULL
    UNION ALL
    SELECT company_id, 'arrived', id, arrived_at FROM trip WHERE arrived_at IS NOT NULL
    UNION ALL
    SELECT c.company_id, 'change_plan', c.id, c.changed_at FROM trip_purpose_change c
) e
WHERE e.company_id = :company_id
  AND NOT EXISTS (SELECT 1 FROM location_fix f
                  WHERE f.company_id = e.company_id AND f.event_kind = e.event_kind
                    AND f.subject_id = e.subject_id)
  AND NOT EXISTS (SELECT 1 FROM missing_location_event m
                  WHERE m.company_id = e.company_id AND m.event_kind = e.event_kind
                    AND m.subject_id = e.subject_id)
ORDER BY e.occurred_at
```

---

## Kilometraje
### K-14 — Calculado con razon terminal, o no calculado con fecha

**Invariante** — debe devolver cero filas

La otra mitad de `ck_trip_mileage_calculated_facts`, que K-02 no cubre: un `calculated` NO lleva razon terminal —no hubo excepcion que explicar— y un estado no calculado no lleva fecha de calculo.  
*Verificado inyectando la violacion:* la base la **rechazo** con `23514` por `ck_trip_mileage_calculated_facts`. La garantia es esa restriccion; la consulta confirma que sigue puesta.

```sql
SELECT id, company_id, trip_id, state, total_meters, calculated_at, terminal_reason
FROM trip_mileage
WHERE (state = 'calculated' AND terminal_reason IS NOT NULL)
   OR (state <> 'calculated' AND calculated_at IS NOT NULL)
```
### K-01 — Mas de un kilometraje por viaje

**Invariante** — debe devolver cero filas

Un viaje, un kilometraje oficial. Un trabajo de fondo duplicado no puede crear un segundo hecho (RTE06 §27).  
*Verificado inyectando la violacion:* la base la **rechazo** con `23505` por `uq_trip_mileage_trip`. La garantia es esa restriccion; la consulta confirma que sigue puesta.

```sql
SELECT company_id, trip_id, count(*) AS cuantos
FROM trip_mileage
GROUP BY company_id, trip_id
HAVING count(*) > 1
```
### K-02 — Total publicado en un estado que no es `calculated`

**Invariante** — debe devolver cero filas

LA consulta que comprueba que NUNCA se publica un total parcial (§25). Un estado no terminal con total seria el numero incompleto presentado como completo que RTE06 prohibe.  
*Verificado inyectando la violacion:* la base la **rechazo** con `23514` por `ck_trip_mileage_calculated_facts`. La garantia es esa restriccion; la consulta confirma que sigue puesta.

```sql
SELECT id, company_id, trip_id, state, total_meters, calculated_at, terminal_reason
FROM trip_mileage
WHERE (state = 'calculated' AND (total_meters IS NULL OR calculated_at IS NULL))
   OR (state <> 'calculated' AND total_meters IS NOT NULL)
```
### K-03 — Estado de excepcion sin razon terminal

**Invariante** — debe devolver cero filas

'No calculable' sin decir QUE waypoint faltaba obliga a reconstruirlo a mano cada vez.

```sql
SELECT id, company_id, trip_id, state, terminal_reason
FROM trip_mileage
WHERE state IN ('not_calculable', 'calculation_failed') AND terminal_reason IS NULL
```
### K-04 — Pendientes sin camino de salida

**Invariante** — debe devolver cero filas

ESTE es el `Pending` permanente que §24 prohibe: sin cita de reintento o con los intentos agotados. Un pendiente con fecha futura NO es un defecto: es el backoff funcionando.

```sql
SELECT id, company_id, trip_id, state, attempt_count, next_attempt_at, last_error
FROM trip_mileage
WHERE state = 'pending_calculation'
  AND (next_attempt_at IS NULL OR attempt_count >= 5)
```
### K-05 — Total que no cuadra con la suma de sus tramos

**Invariante** — debe devolver cero filas

El kilometraje oficial ES la suma de los tramos. Si no cuadra, el total se escribio por otro camino y la provenance no lo explica.  
*Verificado inyectando la violacion:* nada impide escribirla y la consulta la **encontro**. Aqui la consulta es la unica defensa.

```sql
SELECT m.id, m.trip_id, m.total_meters,
       round(sum(s.distance_meters), 2) AS suma_de_tramos,
       count(s.id) AS tramos
FROM trip_mileage m
JOIN trip_mileage_segment s ON s.trip_mileage_id = m.id AND s.company_id = m.company_id
WHERE m.state = 'calculated'
GROUP BY m.id, m.trip_id, m.total_meters
HAVING round(sum(s.distance_meters), 2) <> round(m.total_meters, 2)
```
### K-06 — Tramo mas corto que la linea recta

**Invariante** — debe devolver cero filas

GEOMETRICAMENTE IMPOSIBLE: por carretera nunca se va menos que en linea recta. Es la comprobacion que atrapa el motor de routing ajustando coordenadas fuera de su grafo — medido: dos puntos a 1.073 km devolvieron 10 km de 'ruta'.  
*Verificado inyectando la violacion:* nada impide escribirla y la consulta la **encontro**. Aqui la consulta es la unica defensa.

```sql
SELECT s.id, s.trip_mileage_id, s.sequence, s.distance_meters, s.haversine_meters,
       s.provider, s.from_event_kind, s.to_event_kind
FROM trip_mileage_segment s
WHERE s.haversine_meters IS NOT NULL
  AND s.distance_meters < s.haversine_meters
```
### K-07 — Secuencia de tramos con hueco o duplicada

**Invariante** — debe devolver cero filas

Los tramos van 1, 2, 3 sin huecos. Un hueco significa que se perdio un tramo y el total no cubre todo el viaje.  
*Verificado inyectando la violacion:* nada impide escribirla y la consulta la **encontro**. Aqui la consulta es la unica defensa.

```sql
SELECT trip_mileage_id, count(*) AS tramos, min(sequence) AS primero,
       max(sequence) AS ultimo, count(DISTINCT sequence) AS distintos
FROM trip_mileage_segment
GROUP BY trip_mileage_id
HAVING min(sequence) <> 1
    OR max(sequence) <> count(*)
    OR count(DISTINCT sequence) <> count(*)
```
### K-08 — El primer tramo no sale de la salida, o el ultimo no llega

**Invariante** — debe devolver cero filas

La secuencia es Start Trip -> Change Plan(s) -> Arrived. Si el primer tramo no empieza en la salida, se ordeno por hora de llegada o por id en vez de por ocurrencia — invariante 6 del soak.  
*Verificado inyectando la violacion:* nada impide escribirla y la consulta la **encontro**. Aqui la consulta es la unica defensa.

```sql
SELECT s.trip_mileage_id, s.sequence, s.from_event_kind, s.to_event_kind
FROM trip_mileage_segment s
WHERE (s.sequence = 1 AND s.from_event_kind <> 'start_trip')
   OR (s.to_event_kind = 'arrived' AND s.sequence <> (
          SELECT max(o.sequence) FROM trip_mileage_segment o
          WHERE o.trip_mileage_id = s.trip_mileage_id))
```
### K-09 — Tramos consecutivos que no se encadenan

**Informe** — se lee, no se aprueba

INFORME para leer a ojo: el origen de cada tramo debe ser IGUAL al destino del anterior. Si no, la cadena de waypoints se rompio y el total suma distancias que no se recorrieron seguidas.

```sql
SELECT s.trip_mileage_id, s.sequence, s.from_latitude, s.from_longitude,
       lag(s.to_latitude) OVER w AS lat_anterior,
       lag(s.to_longitude) OVER w AS lon_anterior
FROM trip_mileage_segment s
WINDOW w AS (PARTITION BY s.trip_mileage_id ORDER BY s.sequence)
```
### K-10 — Provenance que sobrevive al purgado

**Invariante** — debe devolver cero filas

§28: un kilometraje `calculated` debe seguir explicandose DESPUES de purgar la evidencia cruda. Por eso el tramo COPIA coordenadas, nivel y hora. Una fila aqui significa que esa copia falto y ese tramo quedaria sin sustento el dia del purgado.  
*Verificado inyectando la violacion:* la base la **rechazo** con `23502` por `NOT NULL trip_mileage_segment.from_latitude`. La garantia es esa restriccion; la consulta confirma que sigue puesta.

```sql
SELECT s.id, s.trip_mileage_id, s.sequence,
       (s.from_latitude IS NOT NULL AND s.to_latitude IS NOT NULL) AS tiene_coordenadas,
       (s.from_evidence_level IS NOT NULL AND s.to_evidence_level IS NOT NULL) AS tiene_nivel,
       (s.from_captured_at IS NOT NULL AND s.to_captured_at IS NOT NULL) AS tiene_horas,
       (s.provider IS NOT NULL AND s.method IS NOT NULL) AS tiene_proveedor,
       (s.from_fix_id IS NOT NULL) AS referencia_blanda_viva
FROM trip_mileage_segment s
WHERE s.from_latitude IS NULL OR s.to_latitude IS NULL
   OR s.from_evidence_level IS NULL OR s.to_evidence_level IS NULL
   OR s.from_captured_at IS NULL OR s.to_captured_at IS NULL
   OR s.provider IS NULL OR s.method IS NULL
```
### K-11 — Estado del kilometraje por proveedor

**Informe** — se lee, no se aprueba

INFORME. `provider` es el motor REALMENTE USADO, no el configurado: si aparece `valhalla`, el primario estuvo caido y la reserva respondio. `unconfigured` significa que no hay motor desplegado.

```sql
SELECT m.state, s.provider, s.method, s.provider_version,
       count(DISTINCT m.id) AS viajes, count(s.id) AS tramos,
       round(avg(s.distance_meters)::numeric, 1) AS distancia_media_m
FROM trip_mileage m
LEFT JOIN trip_mileage_segment s ON s.trip_mileage_id = m.id
WHERE m.company_id = :company_id
GROUP BY m.state, s.provider, s.method, s.provider_version
ORDER BY viajes DESC
```
### K-12 — Suma del dia por jornada, con lo no resuelto

**Informe** — se lee, no se aprueba

INFORME, y el que alimenta reportes. `totalmente_resuelta = false` significa que la suma es PARCIAL: §33 prohibe presentarla como si el dia estuviera cerrado. La conversion a millas usa 1609,344 exacto.

```sql
SELECT ws.id AS work_session_id, ws.session_date, u.username,
       count(*) FILTER (WHERE m.state = 'calculated') AS calculados,
       round(sum(m.total_meters) FILTER (WHERE m.state = 'calculated') / 1609.344, 2) AS millas,
       count(*) FILTER (WHERE m.state = 'pending_calculation') AS pendientes,
       count(*) FILTER (WHERE m.state = 'not_calculable') AS no_calculables,
       count(*) FILTER (WHERE m.state = 'calculation_failed') AS fallidos,
       (count(*) FILTER (WHERE m.state <> 'calculated') = 0) AS totalmente_resuelta
FROM work_session ws
JOIN "user" u ON u.id = ws.user_id
JOIN trip t ON t.work_session_id = ws.id AND t.company_id = ws.company_id
JOIN trip_mileage m ON m.trip_id = t.id AND m.company_id = t.company_id
WHERE ws.company_id = :company_id
GROUP BY ws.id, ws.session_date, u.username
ORDER BY ws.session_date DESC
```
### K-13 — Viajes terminados sin fila de kilometraje

**Informe** — se lee, no se aprueba

INFORME con matiz importante: la fila se crea al terminar el viaje, en la misma transaccion. Filas aqui son viajes ANTERIORES a la migracion 0010, y eso es DELIBERADO — fabricarles kilometraje exigiria waypoints que nunca se capturaron. Un viaje terminado DESPUES del despliegue en esta lista si es un hallazgo.

```sql
SELECT t.id AS trip_id, t.company_id, t.status, t.arrived_at, t.ended_at
FROM trip t
WHERE t.company_id = :company_id
  AND t.status IN ('arrived', 'closed', 'interrupted')
  AND NOT EXISTS (SELECT 1 FROM trip_mileage m
                  WHERE m.trip_id = t.id AND m.company_id = t.company_id)
ORDER BY t.arrived_at
```

---

## Correlacion offline
### X-01 — Clave de accion duplicada dentro de una empresa

**Invariante** — debe devolver cero filas

La clave del cliente identifica UNA accion. Duplicarla significaria que un reenvio creo una segunda fila, y el indice unico parcial lo impide.

```sql
SELECT 'work_session' AS tabla, company_id, client_action_key, count(*) AS cuantas
FROM work_session WHERE client_action_key IS NOT NULL
GROUP BY company_id, client_action_key HAVING count(*) > 1
UNION ALL
SELECT 'trip', company_id, client_action_key, count(*)
FROM trip WHERE client_action_key IS NOT NULL
GROUP BY company_id, client_action_key HAVING count(*) > 1
UNION ALL
SELECT 'trip_purpose_change', company_id, client_action_key, count(*)
FROM trip_purpose_change WHERE client_action_key IS NOT NULL
GROUP BY company_id, client_action_key HAVING count(*) > 1
```
### X-02 — Cobertura de la clave de accion

**Informe** — se lee, no se aprueba

INFORME. `sin_clave` son filas creadas ANTES de la migracion 0013, o por un camino que no envio la cabecera. Es esperado en datos historicos; una proporcion alta en filas NUEVAS significa que el cliente no esta enviando la clave y la correlacion offline no funcionaria.

```sql
SELECT 'work_session' AS tabla,
       count(*) AS filas,
       count(client_action_key) AS con_clave,
       count(*) - count(client_action_key) AS sin_clave
FROM work_session WHERE company_id = :company_id
UNION ALL
SELECT 'trip', count(*), count(client_action_key), count(*) - count(client_action_key)
FROM trip WHERE company_id = :company_id
UNION ALL
SELECT 'trip_purpose_change', count(*), count(client_action_key), count(*) - count(client_action_key)
FROM trip_purpose_change WHERE company_id = :company_id
```
### X-03 — Retraso de sincronizacion de la evidencia

**Informe** — se lee, no se aprueba

INFORME. `sincronizados_tarde` cuenta la evidencia que espero en el dispositivo: es la prueba de que la durabilidad offline funciona. Cero podria significar que nadie ha trabajado sin cobertura, o que la evidencia se esta perdiendo.

```sql
SELECT f.event_kind,
       count(*) AS puntos,
       round(avg(EXTRACT(EPOCH FROM (f.server_received_at - f.device_captured_at)))::numeric, 1) AS retraso_medio_s,
       round(max(EXTRACT(EPOCH FROM (f.server_received_at - f.device_captured_at)))::numeric, 1) AS retraso_max_s,
       count(*) FILTER (WHERE f.server_received_at - f.device_captured_at > interval '5 minutes') AS sincronizados_tarde
FROM location_fix f
WHERE f.company_id = :company_id
GROUP BY f.event_kind
ORDER BY retraso_max_s DESC NULLS LAST
```

---

## Integridad historica
### H-01 — Hechos append-only modificados despues de crearse

**Invariante** — debe devolver cero filas

Estas tres tablas son ESTRICTAMENTE append-only por disparador. Un `updated_at` posterior a `created_at` significa que el disparador estuvo desactivado cuando alguien las toco.  
*Verificado inyectando la violacion:* la base la **rechazo** con `P0001` por `trg_location_fix_append_only`. La garantia es esa restriccion; la consulta confirma que sigue puesta.

```sql
SELECT 'location_fix' AS tabla, id, created_at, updated_at
FROM location_fix WHERE updated_at > created_at + interval '1 second'
UNION ALL
SELECT 'missing_location_event', id, created_at, updated_at
FROM missing_location_event WHERE updated_at > created_at + interval '1 second'
UNION ALL
SELECT 'trip_mileage_segment', id, created_at, updated_at
FROM trip_mileage_segment WHERE updated_at > created_at + interval '1 second'
```
### H-02 — Disparadores de proteccion presentes y activos

**Informe** — se lee, no se aprueba

INFORME CRITICO. Si falta uno o dice DESACTIVADO, la garantia correspondiente DEJO DE EXISTIR aunque el codigo no haya cambiado. Deben estar los de `audit_event`, `integration_event`, `platform_audit_event`, `platform_health_check_run`, `location_fix`, `missing_location_event` y `trip_mileage_segment` — dos por tabla.

```sql
SELECT c.relname AS tabla, t.tgname AS disparador,
       CASE t.tgenabled WHEN 'O' THEN 'activo' WHEN 'D' THEN 'DESACTIVADO'
            ELSE t.tgenabled::text END AS estado
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
WHERE NOT t.tgisinternal
  AND (t.tgname LIKE '%append_only%' OR t.tgname LIKE '%no_truncate%')
ORDER BY c.relname, t.tgname
```
### H-03 — Restricciones que sostienen los invariantes

**Informe** — se lee, no se aprueba

INFORME CRITICO. Cada una sostiene un invariante documentado. La que FALTE de esta lista es una garantia que ya no existe. Deben aparecer las 13.

```sql
SELECT conname AS restriccion, conrelid::regclass AS tabla,
       CASE contype WHEN 'c' THEN 'CHECK' WHEN 'u' THEN 'UNIQUE'
            WHEN 'x' THEN 'EXCLUDE' WHEN 'f' THEN 'FK' ELSE contype::text END AS tipo
FROM pg_constraint
WHERE conname IN (
    'ex_vehicle_assignment_no_overlap',
    'ck_vehicle_assignment_period',
    'ck_location_fix_evidence_level',
    'ck_location_fix_event_subject',
    'ck_location_fix_coordinates',
    'ck_location_fix_cached_age',
    'ck_trip_mileage_calculated_facts',
    'ck_trip_mileage_terminal_needs_reason',
    'ck_missing_location_notification_delivered',
    'uq_missing_location_notification_channel',
    'uq_trip_mileage_trip',
    'ck_activity_execution_terminal_facts',
    'uq_user_company_user_company'
)
ORDER BY conrelid::regclass::text, conname
```
### H-04 — Indices unicos de correlacion e idempotencia

**Informe** — se lee, no se aprueba

INFORME CRITICO. Estos indices SON la idempotencia: sin ellos el reenvio de la cola offline podria duplicar hechos. Deben aparecer los 8 y todos como unicos.

```sql
SELECT indexname AS indice, tablename AS tabla, indexdef LIKE '%UNIQUE%' AS es_unico
FROM pg_indexes
WHERE indexname IN (
    'uq_location_fix_event',
    'uq_missing_location_event',
    'uq_vehicle_assignment_current',
    'uq_work_session_client_action_key',
    'uq_trip_client_action_key',
    'uq_trip_purpose_change_client_action_key',
    'uq_trip_mileage_segment_sequence',
    'uq_activity_execution_trip'
)
ORDER BY tablename, indexname
```
### H-05 — Version del esquema aplicada

**Informe** — se lee, no se aprueba

INFORME. Debe haber UNA sola fila. Tras el cierre final de RTE06 el valor esperado es `0013_client_action_key`. Un valor anterior significa que ese entorno no tiene las correcciones.

```sql
SELECT version_num AS migracion_aplicada FROM alembic_version
```

---

## Auditoria
### D-01 — Eventos de auditoria sin actor

**Informe** — se lee, no se aprueba

INFORME. `trip_mileage` se excluye a proposito: sus transiciones las hace un trabajo de fondo y no tienen actor humano. Otro tipo de entidad sin actor si merece una mirada.

```sql
SELECT id, company_id, entity_type, action, actor_user_id, occurred_at
FROM audit_event
WHERE actor_user_id IS NULL
  AND entity_type NOT IN ('trip_mileage')
ORDER BY occurred_at DESC
```
### D-02 — Coordenadas filtradas en la traza de auditoria

**Invariante** — debe devolver cero filas

§35: la traza registra tipo de evento, sujeto, nivel de evidencia y hora — NUNCA latitud ni longitud. Una fila aqui es una fuga de ubicacion en un registro que se conserva para siempre.  
*Verificado inyectando la violacion:* nada impide escribirla y la consulta la **encontro**. Aqui la consulta es la unica defensa.

```sql
SELECT id, company_id, entity_type, action, occurred_at
FROM audit_event
WHERE changes::text ~* '(latitude|longitude|"lat"|"lon")'
```
### D-03 — Transiciones de kilometraje auditadas

**Informe** — se lee, no se aprueba

INFORME. Deben aparecer `calculated` y `terminalized`. Su ausencia con kilometrajes calculados en la base significa que la auditoria no se esta escribiendo.

```sql
SELECT action, count(*) AS cuantas, min(occurred_at) AS primera, max(occurred_at) AS ultima
FROM audit_event
WHERE company_id = :company_id AND entity_type = 'trip_mileage'
GROUP BY action ORDER BY cuantas DESC
```
### D-04 — Actividad de auditoria por tipo de entidad

**Informe** — se lee, no se aprueba

INFORME. Vista general de lo que el sistema esta registrando.

```sql
SELECT entity_type, action, count(*) AS cuantas
FROM audit_event
WHERE company_id = :company_id
GROUP BY entity_type, action
ORDER BY entity_type, cuantas DESC
```
### D-05 — Claves de idempotencia y su caducidad

**Informe** — se lee, no se aprueba

INFORME. Se purgan cada hora, asi que muchas caducadas significa que el barrido no esta corriendo. IMPORTANTE: esta tabla NO es el ancla de correlacion precisamente porque se purga — para eso esta `client_action_key`.

```sql
SELECT scope, count(*) AS cuantas,
       count(*) FILTER (WHERE expires_at < now()) AS caducadas,
       min(created_at) AS mas_antigua
FROM idempotency_record
WHERE company_id = :company_id
GROUP BY scope ORDER BY cuantas DESC
```

## Lo que estas consultas NO prueban

Dicho explicitamente para que nadie las lea como mas de lo que son:

1. **No sustituyen a los tests.** Comprueban el estado en reposo; no comprueban
   que la API rechace lo que debe rechazar. Un 403 que deberia ser 404 no deja
   rastro aqui.
2. **Cero filas en una base vacia no dice nada.** Sobre un entorno recien
   sembrado casi todas devuelven cero por falta de datos, no por correccion. El
   veredicto `DETECTA`/`RECHAZA` de arriba es lo que hace significativo el cero;
   el cero por si solo, no.
3. **`L-14` y `K-04` tienen falsos positivos por diseno.** Un evento sin punto
   dentro de la ventana de recuperacion, o un pendiente con cita futura, son el
   mecanismo funcionando. Se leen con la antiguedad delante.
4. **No cubren el frontend.** Los permisos de interfaz son experiencia de
   usuario, no control (invariante 8): no hay nada que consultar en la base.
5. **La precision de campo no se audita desde SQL.** `L-09` describe la
   distribucion que se observo; **no** dice si los umbrales estan bien
   calibrados. Eso es la validacion de campo de CER, con dispositivos fisicos.

## Nota sobre `K-10`

`K-10` merece una aclaracion porque su resultado sorprende: **no puede devolver
filas nunca.** Todas las columnas de provenance que comprueba
(`from_latitude`, `from_evidence_level`, `from_captured_at`, `provider`,
`method`) son `NOT NULL` en la tabla. La inyeccion lo confirmo con `23502`.

No se elimina: documenta, de forma ejecutable, que la garantia de §28 —un
kilometraje `calculated` sigue explicandose despues de purgar la evidencia
cruda— la sostiene el esquema y no una convencion. Si alguien aflojara esos
`NOT NULL` en una migracion futura, la consulta empezaria a devolver filas y
esta seccion quedaria desmentida por su propia herramienta.
