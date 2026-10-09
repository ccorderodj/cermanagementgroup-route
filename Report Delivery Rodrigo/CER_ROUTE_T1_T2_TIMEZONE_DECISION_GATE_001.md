# CER Route · T-1/T-2 · Puerta de decisión: fuente de zona horaria

**Documento 001** · 9 de octubre de 2026
**Etapa:** §6 de las instrucciones T-1/T-2 — verificación previa obligatoria.
**Rama:** `feature/t1-t2-timezone-business-day`

---

## Status

`BLOCKED — pendiente de decisión del Product Owner`

No existe una zona IANA en el sistema. Todo lo que T-1/T-2 exige —el «hoy» de
cada supervisor y sus horas locales— depende de crear esa fuente, y el §6 prohíbe
crearla sin aprobación. **No se ha cambiado código, esquema ni datos.** T-1/T-2
**no** se declara completado.

Este documento contiene el AS-BUILT temporal, la verificación, una propuesta
con alternativa y **seis decisiones concretas** (§7). Con ellas aprobadas, la
implementación puede empezar sin más preguntas.

---

## 1 · Respuesta corta a §6.1

> ¿Hay una zona IANA ya disponible?

**No.** `CONFIRMED` sobre el código vigente (`dev` en `9d5d5cc`):

| Dónde se buscó | Resultado |
|---|---|
| Modelos, schemas y servicios (`zoneinfo`, `pytz`, `time_zone`, `tz`…) | ninguna referencia |
| `SupervisorProfile`, `Users`, `Company` | sin campo de zona |
| Lo que envía el cliente | sólo `utc_offset_minutes`, de `getTimezoneOffset()` |
| `Intl.DateTimeFormat().resolvedOptions().timeZone` | **no se usa en ningún sitio** |

El navegador del supervisor **sí conoce** su zona IANA (`America/New_York`);
simplemente nunca se pide. Es la pieza más barata de la propuesta.

---

## 2 · AS-BUILT temporal

### 2.1 · Productores

| Dato | Quién lo produce | Dónde se guarda |
|---|---|---|
| Instantes (`started_at`, `ended_at`, salidas, llegadas, actividades) | servidor, validando la evidencia del dispositivo | `timestamptz` — correcto, no se toca (TR-01) |
| `utc_offset_minutes` | `captureTimeEvidence()` en `shared/lib/utils/utils.ts`: `-getTimezoneOffset()` | `WorkSession.start_utc_offset_minutes` y `end_utc_offset_minutes` |
| Offset de `Start Trip`, `Arrived`, actividades | mismo helper | **se recibe y no se guarda** — los instantes son absolutos, así que no se pierde nada |
| `session_date` | `_session_date_from()` en `worksessions/service.py`: instante + offset del inicio; **UTC si no hay offset** | `WorkSession.session_date` (`date`), congelada al inicio — correcto (TR-03) |

### 2.2 · Consumidores

| Consumidor | Regla actual |
|---|---|
| `live/dao.py::business_day(company_id)` | «hoy» = ahora + **offset de la última jornada iniciada por cualquier supervisor de la compañía**; UTC si ninguna lo tiene |
| `live/router.py` (Today) | **un solo día para todos**: `today_rows(company, dia)` filtra `session_date == dia` |
| `activityexplorer/dao.py::business_day_actual` | reutiliza la misma función, para el ancla por defecto de User Activity |
| Today, columna `since` | `formatSince` → `toLocaleTimeString([])`: **zona del navegador del administrador** |
| User Activity, horas de tarjeta | `formatClock` → `toLocaleTimeString('en-US')`: **zona del navegador del administrador** |
| Filtros día/semana/mes/año | agrupan por `session_date` — correcto (TR-05), no se toca |

### 2.3 · Lo que está bien y se conserva

- Los 25 instantes son `timestamptz` (verificación de contrato temporal, 08/10).
- **Ningún SQL de `app/` deriva una fecha de la zona de sesión de PostgreSQL**:
  no hay `CURRENT_DATE` ni `::date`; los `func.now()` son instantes.
- `session_date` es la fecha local de inicio y no se recalcula al cruzar
  medianoche.
- Las acciones offline conservan su instante de ocurrencia
  (`_resolve_occurrence`), y la fecha de jornada sale de ese instante, no del de
  sincronización.

---

## 3 · Defectos confirmados en el AS-BUILT

| # | Defecto | AC | Evidencia |
|---|---|---|---|
| D1 | El «hoy» de todos lo decide la **última jornada de cualquier supervisor** | AC01, AC02 | `business_day()`, `order_by(started_at.desc()).limit(1)` |
| D2 | Sin offsets, «hoy» es **UTC**: en el Este, de 20:00 a 24:00 (verano) el día ya es mañana | AC01 | mismo código |
| D3 | Today y User Activity formatean en la **zona del navegador del administrador** | AC05 | `formatSince`, `formatClock` |
| D4 | Today filtra **un solo día para toda la compañía**: una jornada nocturna activa **desaparece a medianoche** y el supervisor sale `Not started` | AC03 | `today_rows`, `session_date == dia` |
| D5 | Un offset fijo **no anticipa el cambio de horario** | AC08, TR-02 | datos reales, §4 |

D4 es la cara nocturna del mismo problema que el diagnóstico de jornadas sin
cerrar encontró de día. **Su arreglo aquí es sólo de presentación del estado
vivo**; cerrar o recuperar jornadas sigue siendo P-2.

---

## 4 · Lo que dicen los datos reales

Copia local de `cerroute` (`db-dev-cer-route`, datos reales hasta el 08/10;
**no es producción**). Sólo lectura:

```
offset   jornadas  supervisores  desde        hasta
 -240        79          8       2026-10-01   2026-10-08    ← Este, horario de verano
 -360         1          1       2026-09-28   2026-09-28    ← otra zona, un caso
 NULL         0

jornadas cuyo offset cambió entre inicio y fin:   1
jornadas que terminan después de su medianoche local: 8
```

**La consecuencia práctica, con fecha:** el **1 de noviembre de 2026** el Este
pasa de −240 a −300. Cualquier regla que extrapole el offset guardado dará la
hora con **una hora de error** a partir de ese día, y el «hoy» equivocado entre
las 23:00 y las 24:00. Quedan tres semanas. Por eso la alternativa «sin esquema»
(§5.3) no se recomienda.

---

## 5 · Propuesta (§6.2–6.4)

### 5.1 · Opción A — zona por supervisor + instantánea en la jornada · **recomendada**

**Dos columnas, ambas `NULL`able, ninguna reescritura de datos:**

| Columna | Qué guarda | Quién la escribe |
|---|---|---|
| `supervisor_profile.operational_time_zone` | zona IANA operativa del supervisor | **un administrador**, en el panel de configuración de supervisor que ya existe (un campo más, sin pantalla nueva) |
| `work_session.start_time_zone` | zona IANA **del dispositivo al iniciar** la jornada | el servidor, desde la evidencia del cliente, igual que hoy el offset |

`start_utc_offset_minutes` **se conserva**: sigue siendo evidencia del momento, y
es lo único que tienen las jornadas históricas.

**Cómo se resuelve cada caso:**

| Caso | Resolución |
|---|---|
| «Hoy» de un supervisor | su zona operativa → si no la tiene, la zona de **su propia** jornada más reciente → si no, **zona no determinada** (§7, D3) |
| Supervisor sin jornada hoy | su zona operativa; **nunca** la de otro (TR-04) |
| Supervisor que trabaja en otro huso | la jornada guarda la zona real del dispositivo: sus horas se muestran donde ocurrieron |
| Historia si el perfil cambia | cada jornada usa **su** instantánea; cambiar el perfil no reescribe nada |
| Horas de una jornada | su `start_time_zone` → si es histórica, su offset, rotulado `UTC−04:00`, **nunca** `EDT` (TR-06) |
| DST | `zoneinfo` aplica las reglas históricas. T-1/T-2 sólo convierte **instante → hora local**, que nunca es ambiguo; la ambigüedad de las horas repetidas sólo aparece al convertir hora local → instante, y eso es P-2 |
| Offline | la zona se captura **al encolar**, junto al instante; no se refecha al sincronizar (TR-09) |
| Jornada nocturna | Today muestra el **estado vivo** de una jornada activa aunque su `session_date` sea de ayer (D4); sus métricas siguen atribuidas a su `session_date` (§7, D4) |

**Validación server-side:** la zona sólo se acepta si `zoneinfo` la reconoce. Un
valor desconocido se rechaza con 422 en el perfil y se guarda como `NULL` en la
jornada, que nunca se bloquea por falta de evidencia (D-10).

**Auditoría:** el cambio de zona operativa queda en `audit_event` con quién y
cuándo, reutilizando el registro existente.

**Contrato API, aditivo:** cada fila de Today y cada tarjeta de User Activity
reciben la zona (o el offset) con la que formatear. Ningún campo existente cambia
de tipo. **Aprendizaje de R-1:** un navegador con el bundle anterior en caché
ignora campos nuevos sin romperse, siempre que no se relaje ninguno existente.

**Migración:** añade dos columnas `NULL`, sin relleno. `downgrade` las elimina.
Ningún dato histórico se toca.

### 5.2 · Opción B — sólo la instantánea en la jornada · menor impacto

Igual que A **sin** la columna del perfil ni el campo en el panel.

| | A | B |
|---|---|---|
| Esquema | 2 columnas | 1 columna |
| Configuración de administrador | 1 campo en panel existente | ninguna |
| «Hoy» de un supervisor que nunca ha iniciado jornada | su zona configurada | **no determinada** |
| Supervisor que se muda de zona | el administrador lo actualiza | se corrige solo en su siguiente jornada |
| Fuente de verdad | el administrador | **el dispositivo** (requiere aprobación explícita, §6.5) |

B es aceptable si se acepta que la zona del dispositivo sea la verdad operativa.
Su punto débil es pequeño en la práctica: un supervisor sin ninguna jornada
saldría `Not started` en cualquier caso.

### 5.3 · Opción C — sin esquema, extrapolando el offset · **no recomendada**

Arregla D1 (cada supervisor con su propio offset) sin migración, pero **falla el
1 de noviembre** (§4) e incumple TR-02 y TR-08. Sólo tendría sentido como
remiendo temporal, y no lo propongo.

---

## 6 · Lo que se puede hacer ya, sin aprobación

Preparar las pruebas de los AC que no dependen del modelo elegido:

- **AC01**: que el inicio de jornada de un supervisor no cambie el «hoy» de
  otro. Hoy fallaría (D1), y la prueba es la misma con A o con B.
- **Independencia de la zona de sesión de PostgreSQL**: ejecutar las consultas
  de Today y User Activity con `SET TIME ZONE` distinto de UTC.

**No las he escrito todavía**: prefiero que su forma final salga de la decisión
y no tener que reescribirlas. Si se quiere avanzar en paralelo, son ≈ 1,5 h.

Una nota de la misma familia: la E2E de R-1 que falla de 18:00 a 24:00 hora
local (reporte de workers, §5.2) usa `CURRENT_DATE` de PostgreSQL. Las pruebas de
T-1 fijarán fechas e instantes explícitos, y esa prueba debería alinearse al
implementar, si el PO lo autoriza.

---

## 7 · Decisiones que necesito

| # | Decisión | Mi recomendación |
|---|---|---|
| **D1** | **Opción A, B o C** | **A** |
| **D2** | ¿Se acepta la zona IANA del **dispositivo** como evidencia de la jornada (instantánea)? | **Sí**: es la misma fuente que ya da el offset, y más precisa |
| **D3** | Supervisor **sin zona determinable**: ¿qué «hoy» se usa para él en Today? | Mostrarlo con su estado vivo si tiene jornada activa, y si no, `Not started` **con la marca «zona no determinada»**; nunca UTC como si fuera su hora |
| **D4** | Jornada nocturna activa al pasar medianoche: ¿Today muestra sus millas y actividades? | **Estado vivo sí; métricas de su `session_date`**, que es la regla de H-2. No cambiar el alcance de los acumulados sin decisión |
| **D5** | Jornadas **históricas** sin zona: ¿se muestran en su offset rotulado (`UTC−04:00`)? | **Sí**: es un dato real de ese momento; mostrarlo rotulado no inventa nada |
| **D6** | (sólo con A) ¿Se rellena la zona operativa de los perfiles existentes? | **No automáticamente.** Los administradores la fijan; mientras tanto se usa la de la última jornada propia |

---

## 8 · Estimación de la implementación

Medida con los coeficientes del protocolo y **corregida con el sesgo observado
en H-2 y R-1** (la verificación cuesta más del doble que el cambio).

| Tarea | Volumen | Complejidad | A (h) | B (h) |
|---|---|---|---|---|
| Migración, modelo, validación IANA, auditoría | ~120 LoC | determinista | 1,0 | 0,5 |
| Captura de zona en Start Work y cola offline | ~40 LoC | integración | 0,6 | 0,6 |
| «Hoy» por supervisor y Today por fecha propia (D1, D4) | ~180 LoC | dominio | 1,5 | 1,5 |
| Ancla de User Activity y contrato aditivo | ~60 LoC | determinista | 0,5 | 0,5 |
| Formateo compartido en la zona de la jornada | ~120 LoC | UI | 2,0 | 2,0 |
| Campo en el panel de supervisor | ~60 LoC | UI | 1,0 | — |
| Pruebas de integración: Este/Centro, DST, offline, medianoche, tenant | ~650 LoC | integración | 7,0 | 6,0 |
| E2E con dos navegadores en zonas distintas, escritorio y móvil | ~300 LoC | navegador | 5,0 | 5,0 |
| Regresión completa, verificación contra código anterior, reporte | — | — | 3,5 | 3,5 |
| **Subtotal** | | | **22,1** | **19,6** |
| **Con margen** (+10 % determinista, +30 % integración, +50 % navegador) | | | **≈ 28 h** | **≈ 25 h** |

---

## 9 · Git

| | |
|---|---|
| Rama | `feature/t1-t2-timezone-business-day` |
| Base | `dev` en `9d5d5cc` |
| Cambio | este documento y la instrucción recibida; **ningún código** |
| Commit | `cfbd3bd` |
| MR | **!79** · https://gitlab.com/cermanagementgroup/cermanagementgroup-route/-/merge_requests/79 |
| Fusionado | **No.** CER certifica |

---

## 10 · Siguiente paso

Decisiones D1–D6. Con ellas, la implementación empieza en esta misma rama y
termina en **un solo** documento T-1/T-2 con AC01–AC12, como pide el §12.

P-2, H-3 y H-1 siguen fuera de alcance.
