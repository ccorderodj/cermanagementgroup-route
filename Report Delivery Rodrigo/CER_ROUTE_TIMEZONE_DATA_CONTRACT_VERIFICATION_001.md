# CER Route · Verificación del contrato temporal

**Documento 001** · 8 de octubre de 2026
**Tipo:** verificación de solo lectura · **Estado:** `VERIFICATION ONLY — NOT IMPLEMENTED`
**Alcance:** `WorkSession`, `Trip`, `ActivityExecution` · precede a H-2 y H-3

> No se modificó código ni se ejecutó ninguna migración. El formato almacenado
> se verificó **empíricamente** contra el esquema real antes de proponer nada,
> que es lo que la instrucción exige.

---

## Conclusión primero

**El almacenamiento es correcto y no requiere ninguna corrección.** Los tres
modelos usan `timestamp with time zone` en todas sus columnas de instante, sin
una sola excepción. **No se propone ningún reemplazo de campos ni conversión de
datos históricos, porque la evidencia demuestra que no hacen falta.**

Los problemas están **aguas abajo del almacenamiento**: en cómo se deriva el día
de negocio y en qué zona se pintan las horas. Son cuatro, y ninguno exige tocar
la base.

---

# 1 · Contrato temporal AS-BUILT

## 1.1 · Tipos reales en PostgreSQL · `CONFIRMED` empíricamente

Consulta de solo lectura a `information_schema.columns` sobre el esquema vivo
—sin tocar ningún dato de negocio—:

```
activity_execution   created_at                   timestamp with time zone
activity_execution   ended_at                     timestamp with time zone
activity_execution   ended_received_at            timestamp with time zone
activity_execution   started_at                   timestamp with time zone
activity_execution   started_received_at          timestamp with time zone
activity_execution   updated_at                   timestamp with time zone
trip                 arrived_at                   timestamp with time zone
trip                 arrived_received_at          timestamp with time zone
trip                 created_at                   timestamp with time zone
trip                 ended_at                     timestamp with time zone
trip                 ended_received_at            timestamp with time zone
trip                 started_at                   timestamp with time zone
trip                 started_received_at          timestamp with time zone
trip                 updated_at                   timestamp with time zone
work_session         created_at                   timestamp with time zone
work_session         end_device_captured_at       timestamp with time zone
work_session         end_utc_offset_minutes       integer
work_session         ended_at                     timestamp with time zone
work_session         ended_received_at            timestamp with time zone
work_session         session_date                 date
work_session         start_device_captured_at     timestamp with time zone
work_session         start_utc_offset_minutes     integer
work_session         started_at                   timestamp with time zone
work_session         started_received_at          timestamp with time zone
work_session         updated_at                   timestamp with time zone
```

**Cero columnas `timestamp without time zone`.** Qué representa realmente cada
tipo:

| Tipo | Qué guarda PostgreSQL | Qué significa aquí |
|---|---|---|
| `timestamptz` | un **instante absoluto**, normalizado a UTC internamente | el momento en que ocurrió el hecho, sin ambigüedad |
| `date` | una fecha de calendario, **sin** zona | el día de negocio ya resuelto y congelado |
| `integer` (offset) | minutos al **este** de UTC | en qué zona trabajaba el dispositivo |

El modelo base lo declara y explica por qué
([`core/models/TimeStamped.py:10-15`](app/core/models/TimeStamped.py#L10)): antes
convivían `timestamp` naive y `timestamptz` en la misma fila, y compararlos en
Python lanza `TypeError`. Se unificó.

## 1.2 · Normalización: UTC siempre, nunca la hora local del servidor

| Camino | Mecanismo | Evidencia |
|---|---|---|
| Recepción | `datetime.now(timezone.utc)` | `worksessions/service.py` |
| Evidencia del cliente | `_as_utc()` — un `datetime` sin zona se **interpreta** como UTC, no se rechaza | [`service.py:63-69`](app/routers_api/worksessions/service.py#L63) |
| Defecto de columna | `server_default=now()`, que en PostgreSQL es `timestamptz` | verificado: `pg_typeof(now()) = timestamp with time zone` |

**En ningún punto se usa la hora local del servidor.** La sonda confirmó que el
`TimeZone` de la sesión del entorno inspeccionado es `America/Guatemala`, y en
§2.5 se demuestra que ese valor **no influye en ningún resultado**.

## 1.3 · Captura de la hora del dispositivo

**Cliente** — [`shared/lib/utils/utils.ts:407`](app/components/react/shared/lib/utils/utils.ts#L407):

```ts
export function captureTimeEvidence(): DeviceTimeEvidence {
    return {
        device_captured_at: new Date().toISOString(),
        // `getTimezoneOffset()` devuelve minutos al OESTE de UTC; el backend
        // espera minutos al ESTE (D-10), de ahí el signo invertido.
        utc_offset_minutes: -new Date().getTimezoneOffset(),
    };
}
```

Se invoca **al construir la acción**, no al enviarla: `worksession.start/end`,
`trip.plan/start/change_plan/arrive`, `activity.start/complete/leave`. La cola lo
confirma ([`offlineQueue.ts:319`](app/components/react/shared/lib/offlineQueue/offlineQueue.ts#L319)):
*«`device_captured_at` incluidos. Nada los recalcula al enviar»*.

**Servidor — y aquí está la asimetría:**

| Modelo | Acepta `device_captured_at` | Acepta `utc_offset_minutes` | **Almacena** la hora cruda | **Almacena** el offset | Almacena la procedencia |
|---|---|---|---|---|---|
| `WorkSession` | sí | sí | **sí** | **sí** | sí (`*_at_source`) |
| `Trip` | sí | sí | **no** | **no** | **no** |
| `ActivityExecution` | sí | sí | **no** | **no** | sí (`*_at_source`) |
| `RouteLocationPoint` | sí | — | **sí** | — | — |

Es decir: **los tres contratos reciben el offset y sólo `WorkSession` lo
conserva.** En `Trip` y `ActivityExecution` se usa para derivar `*_at` y después
se descarta.

Evidencia: [`trips/schemas.py:36-46`](app/routers_api/trips/schemas.py#L36) ·
[`activities/schemas.py:26-48`](app/routers_api/activities/schemas.py#L26) ·
búsqueda de `utc_offset_minutes` en todos los modelos: sólo `work_session`.

## 1.4 · Resolución de la ocurrencia

[`worksessions/service.py:75`](app/routers_api/worksessions/service.py#L75), reutilizada
por `trips/service.py:582` y `activities/service.py:52` — **una sola
implementación**, no tres.

```python
if device_captured_at is None:            → SERVER_RECEIPT
if ocurrencia > recibido + 2 min:         → SERVER_RECEIPT   (futuro imposible)
if ocurrencia < recibido - 7 días:        → SERVER_RECEIPT   (evidencia vieja)
if ocurrencia < not_before:               → SERVER_RECEIPT   (viola el ciclo)
else:                                      → DEVICE
```

Constantes: `_FUTURE_EVIDENCE_TOLERANCE = 2 min`, `_MAX_EVIDENCE_AGE = 7 días`.
La evidencia rechazada **se guarda igual** en `WorkSession`, y el rechazo nunca
bloquea la acción.

## 1.5 · `session_date` y el cruce de medianoche

[`worksessions/service.py:121`](app/routers_api/worksessions/service.py#L121):

```python
def _session_date_from(occurred_at_utc, utc_offset_minutes) -> date:
    if utc_offset_minutes is None:
        return occurred_at_utc.date()          # cae a UTC
    return (occurred_at_utc + timedelta(minutes=utc_offset_minutes)).date()
```

**Se calcula una vez, al crear la jornada, y nunca se recalcula** — ni en
`End Work` ni por ningún otro camino
([`worksessions/models.py:69-72`](app/routers_api/worksessions/models.py#L69)).

**Una jornada que cruza medianoche conserva la fecha en que empezó.** Es una
decisión explícita (D-10) y es la correcta: un turno de noche pertenece al día
en que se abrió.

## 1.6 · Qué timestamps alimentan Current Activity, Last Activity y Since

| Campo | Fuente | Tipo |
|---|---|---|
| `status = activity` | `ActivityExecution.status = IN_PROGRESS` | — |
| `since` (activity) | `ActivityExecution.started_at` | `timestamptz` |
| `since` (route) | `Trip.started_at` | `timestamptz` |
| `since` (working) | `Trip.arrived_at` ?? `WorkSession.started_at` | `timestamptz` |
| `since` (ended) | `WorkSession.ended_at` | `timestamptz` |
| `activity_label` | `Trip.current_purpose` (no es un instante) | — |
| Selección del día | `WorkSession.session_date` | `date` |

Evidencia: [`live/dao.py:271-285`](app/routers_api/live/dao.py#L271).

**Todos los instantes que se muestran son `timestamptz`.** Ninguno se deriva de
una conversión de zona en SQL.

## 1.7 · Presentación en el cliente

| Pantalla | Función | Zona usada |
|---|---|---|
| Today / Live | `toLocaleTimeString([], …)` ([`RouteLive/.../index.ts:154`](app/components/react/entities/RouteLive/model/types/index.ts#L154)) | **la del navegador del administrador** |
| Activity Explorer | `toLocaleTimeString('en-US', …)` ([`RouteActivityExplorer/.../index.ts:182`](app/components/react/entities/RouteActivityExplorer/model/types/index.ts#L182)) | **la del navegador del administrador** |

## 1.8 · El día de negocio

[`live/dao.py:55-71`](app/routers_api/live/dao.py#L55):

```python
desfase = (último start_utc_offset_minutes no nulo de la COMPAÑÍA)
ahora = datetime.now(timezone.utc)
if desfase is None:
    return ahora.date()                              # ← cae a UTC
return (ahora + timedelta(minutes=desfase)).date()
```

El Activity Explorer **reutiliza esta función**, no la reimplementa
([`activityexplorer/dao.py:61-73`](app/routers_api/activityexplorer/dao.py#L61)),
conforme al invariante 9. Las dos pantallas responden siempre lo mismo a «¿qué
día es hoy?».

---

# 2 · Inconsistencias confirmadas

### I-1 · `CONFIRMED` — El día de negocio de toda la compañía sale de una sola jornada

`business_day()` toma el offset de **la última jornada iniciada en la compañía**
y se lo aplica a `now()`. No hay zona horaria de compañía ni de supervisor en el
modelo.

Con supervisores en husos distintos, el día de la pantalla lo decide quien
arrancó más recientemente. Los de otro huso quedan evaluados contra un día que
no es el suyo cerca de los bordes.

### I-2 · `CONFIRMED` — Sin offset conocido, el día cae a UTC

Si ninguna jornada de la compañía tiene `start_utc_offset_minutes`, el día es el
de UTC. Para una flota en US Eastern (UTC−5/−4) eso significa que **la pantalla
cambia de día a las 19:00 o 20:00 hora local**, no a medianoche.

Afecta a una compañía recién creada y a cualquiera cuyos clientes no envíen el
offset. En el despliegue actual el cliente siempre lo envía, de modo que la
ventana es el arranque de un tenant nuevo.

### I-3 · `CONFIRMED` — `Trip` y `ActivityExecution` descartan el offset recibido

Lo aceptan en el contrato y no lo almacenan (§1.3). Consecuencia: **no se puede
reconstruir la hora local de una llegada ni de una actividad.** Sólo se puede
reconstruir la de la jornada, con el offset de `WorkSession`.

Hoy no produce un dato incorrecto —todo se agrupa por `session_date`—, pero
cierra la puerta a mostrar «llegó a las 14:05 **hora del supervisor**» sin
asumir que su zona no cambió durante el día.

### I-4 · `CONFIRMED` — El día usa el reloj del supervisor; la hora, el del administrador

El servidor decide `session_date` con el offset del **dispositivo del
supervisor**; el navegador pinta `Since` con la zona del **administrador**
(§1.7). Son dos relojes distintos para la misma fila.

Si el administrador abre Today desde otro huso, **`Since 6:30 AM` no es la hora
a la que el supervisor empezó.** La pantalla no advierte de qué zona habla.

### I-5 · `PARTIAL` — Dos formatos de hora entre pantallas

Today usa el locale del navegador; el Explorer fija `'en-US'`. Mismo dato,
presentación distinta según la pantalla y la configuración del equipo. Es
cosmético, pero las dos pantallas se leen juntas.

### I-6 · `PENDING VALIDATION` — DST y la ventana del offset obsoleto

`session_date` **es inmune**: se congela al abrir la jornada, con el offset
vigente en ese instante.

`business_day()` **no**: usa el offset de la última jornada iniciada, que tras un
cambio de horario conserva el valor anterior hasta que alguien abre una jornada
nueva. En US Eastern el cambio ocurre a las 02:00 del domingo y los supervisores
arrancan hacia las 06:30, así que la ventana es de unas horas de madrugada
dominical, cuando la pantalla no se usa. **Riesgo real pero de impacto bajo**, y
no se ha observado en producción.

### Riesgos descartados con evidencia

| Hipótesis | Veredicto |
|---|---|
| Hay columnas `timestamp` sin zona | **Descartada.** Las 25 columnas inspeccionadas llevan zona |
| El servidor usa su hora local | **Descartada.** `datetime.now(timezone.utc)` y `_as_utc()` |
| El `TimeZone` de PostgreSQL afecta a los registros seleccionados | **Descartada.** Ver §2.5 |
| Los eventos offline se fechan al sincronizar | **Descartada.** Se fechan al encolar, y nada los recalcula |
| Hay tres implementaciones distintas de la regla de ocurrencia | **Descartada.** Una sola, importada por los tres servicios |
| Today y Activity usan días de negocio distintos | **Descartada.** El Explorer reutiliza `business_day` |

### 2.5 · Por qué el `TimeZone` del servidor no cambia qué registros se seleccionan

Es la comprobación que convierte una sospecha razonable en un riesgo
neutralizado, así que se deja con su evidencia.

En PostgreSQL, un `timestamptz` se guarda siempre en UTC; el `TimeZone` de la
sesión sólo interviene al **convertirlo a texto** o al derivar un día con
`::date`, `date_trunc` o `extract` **sin zona explícita**. Si alguna consulta
hiciera eso, el mismo código daría días distintos en el portátil
(`America/Guatemala`) y en App Platform.

Búsqueda sobre `app/routers_api` y `app/db`:

```
grep -rn "date_trunc|::date|func.date\(|cast\(.*Date" --include=*.py
→ sin resultados
```

**Ninguna consulta deriva un día desde un instante.** Todo el agrupamiento por
día usa `WorkSession.session_date`, que ya es `date` y se calculó una vez en
Python con el offset del dispositivo
([`activityexplorer/dao.py:238`](app/routers_api/activityexplorer/dao.py#L238),
[`live/dao.py:114`](app/routers_api/live/dao.py#L114)).

**Respuesta directa a la pregunta 7:** una consulta hecha desde otra zona horaria
**sólo altera la presentación**. No cambia el día seleccionado ni el conjunto de
registros. El día lo decide `business_day()` en el servidor, y ése depende del
offset del supervisor (I-1), nunca del navegador de quien consulta.

---

# 3 · Impacto sobre Today y User Activity

| | Today / Live | Activity Explorer |
|---|---|---|
| Registros seleccionados | correctos: `session_date` | correctos: `session_date` |
| Día de negocio | I-1, I-2, I-6 | **el mismo**, por reutilización |
| Horas mostradas | I-4: zona del administrador | I-4: zona del administrador |
| Formato | locale del navegador | fijo `en-US` (I-5) |
| Cruce de medianoche | correcto | correcto |
| Eventos offline | correctos: hora de encolado | correctos |

**Ningún dato está almacenado incorrectamente.** Lo que puede inducir a error es
**qué hora se enseña** y, en los bordes del día, **qué día se considera hoy**.

Para H-2 y H-3 esto importa de una forma concreta: cuando Today agregue por
supervisor, tendrá que decidir con qué criterio une jornadas que pueden tener
offsets distintos. Si las dos jornadas de un día comparten `session_date`, la
agregación es correcta por construcción — y lo comparten, porque `session_date`
se calcula con el offset de cada una pero la pantalla ya filtra por un único
`dia`. **No hay bloqueo para H-2 ni H-3 por motivos temporales.**

---

# 4 · Corrección mínima recomendada

**Lo que explícitamente NO se propone,** porque la evidencia demuestra que no
hace falta:

- ningún cambio de tipo de columna;
- ninguna migración;
- ninguna conversión de datos históricos;
- ningún reemplazo de campos.

Las correcciones son de **derivación y presentación**, y se ordenan por relación
coste/beneficio.

### M-1 · Mostrar la hora en la zona de la jornada, no en la del administrador *(I-4)*

**La corrección de mayor valor y la única que elimina un dato engañoso.**

El dato necesario **ya está almacenado**: `WorkSession.start_utc_offset_minutes`.
Basta con exponerlo en el contrato de lectura y formatear con él en lugar de
delegar en el navegador, indicando la zona junto a la hora (`6:30 AM (−04:00)`)
para que nadie tenga que suponerla.

- Componentes: `live/schemas.py`, `live/dao.py`, `formatSince`, el panel y la tabla.
- API: **aditivo**.
- Migración: **ninguna**.
- Riesgo: bajo; afecta a la presentación.
- Esfuerzo: **≈ 1,6 h-agente**.

### M-2 · Que el día de negocio no dependa de una sola jornada *(I-1, I-2, I-6)*

Tres opciones, y **la elección no es técnica** (ver §5):

| | Qué hace | Migración |
|---|---|---|
| **a** | zona horaria por compañía, configurable | **sí**, un campo nuevo |
| **b** | el offset más frecuente entre las jornadas recientes, en vez del último | no |
| **c** | el offset del propio supervisor para su fila | no |

La (b) elimina I-6 y suaviza I-1 sin tocar la base. La (a) es la correcta a
largo plazo. La (c) es la más fiel y la que más cambia la consulta.

- Esfuerzo: **≈ 1,2 h** (b) · **≈ 3,0 h** (a, incluida migración y pantalla).

### M-3 · Unificar el formato de hora entre pantallas *(I-5)*

Una función compartida en `shared/lib/utils`, usada por Today y por el Explorer.
Encaja de forma natural dentro de M-1.

- Esfuerzo: **≈ 0,4 h** si va con M-1.

### M-4 · Persistir el offset en `Trip` y `ActivityExecution` *(I-3)*

**No se recomienda ahora.** Requiere dos columnas nuevas por tabla y una
migración, y hoy no corrige ningún dato incorrecto: sólo habilita una capacidad
futura —mostrar la hora local de un evento intermedio— que ninguna pantalla pide
todavía.

Queda anotado como deuda consciente. Si se decidiera, **las filas históricas no
se pueden rellenar**: el offset no se guardó y no se puede inventar. La columna
nacería anulable y los registros anteriores quedarían sin ella, que es lo
honesto.

- Esfuerzo si se aprueba: **≈ 2,5 h**.

### Orden sugerido

**M-1 + M-3 juntas** (≈ 2,0 h): corrigen lo que hoy puede engañar a quien mira,
sin tocar la base ni los contratos de escritura. **M-2** después, cuando el
Product Owner decida entre (a), (b) y (c). **M-4** no entra salvo petición
expresa.

---

# 5 · Decisiones requeridas

**T-1 · ¿Qué define el día de negocio de una compañía?** Hoy es el offset de la
última jornada iniciada. Las opciones son zona de compañía (con migración),
offset más frecuente, u offset por supervisor. Determina M-2.

**T-2 · ¿La hora se muestra en la zona del supervisor o del administrador?** La
recomendación es la del supervisor, indicando la zona. Un administrador que
coordine varios husos podría preferir la suya, pero entonces debe estar
etiquetada igualmente.

**T-3 · ¿Se persiste el offset en viajes y actividades?** Sólo si se quiere
mostrar su hora local. Hoy no hay pantalla que lo pida y las filas históricas no
se podrían completar.

---

# 6 · Limitaciones de esta verificación

1. **La sonda de esquema se ejecutó contra el entorno local**, no contra
   producción. Las dos bases salen de las mismas migraciones de Alembic, así que
   el DDL es el mismo; aun así, confirmarlo en producción es una consulta de
   solo lectura y queda **propuesta, no ejecutada**.
2. **No se midió el `TimeZone` de la sesión en App Platform.** En §2.5 se
   demuestra que no influye en ningún resultado, de modo que el dato es
   informativo y no condiciona ninguna conclusión.
3. **I-6 (DST) no se ha observado en producción**: se deriva del código y de las
   fechas de cambio horario. Queda `PENDING VALIDATION`.
4. **No se ejecutó ninguna prueba.** Este documento no afirma ningún resultado de
   suite.
5. **No se evaluó el comportamiento con un supervisor que cruce husos durante una
   misma jornada.** `session_date` quedaría fijado por el offset de inicio, que
   es la respuesta correcta, pero no está cubierto por ninguna prueba.

---

**Preparado para que el Product Owner decida T-1, T-2 y T-3 antes de iniciar
H-2 y H-3.** Ninguna línea de código, migración ni dato se modificó durante esta
verificación.
