# CER Route · Conciliación Today / User Activity

**Documento 001** · 8 de octubre de 2026
**Tipo:** investigación de solo lectura · **Estado:** `DIAGNOSTIC ONLY — NOT IMPLEMENTED`
**Caso:** supervisora K.A., 08/10/2026 — 125,5 mi en el consolidado frente a 62,5 mi visibles

> No se modificó código, kilometraje, datos históricos, interfaces, permisos ni
> estados operativos.

---

## Causa raíz · `CONFIRMED` por código

**El resumen de User Activity se arma con dos consultas distintas que recorren
conjuntos distintos de viajes.**

[`activityexplorer/router.py:117-124`](app/routers_api/activityexplorer/router.py#L117):

```python
summary=ExplorerSummary(
    official_miles=millas_oficiales(datos["metros"] ...),  # ← agregados_por_dia
    mileage_pending=bool(datos and datos["pendientes"]),   # ← agregados_por_dia
    activity_seconds=datos["segundos"] ...,                # ← agregados_por_dia
    has_open_activity=bool(datos and datos["abiertos"]),   # ← agregados_por_dia
    activities=len(paradas),                               # ← paradas_del_dia
),
activities=[ExplorerActivity(**p) for p in paradas],       # ← paradas_del_dia
```

Las dos fuentes no son equivalentes:

| | Parte de | Incluye |
|---|---|---|
| `agregados_por_dia` ([dao.py:215](app/routers_api/activityexplorer/dao.py#L215)) | `WorkSession` → **INNER JOIN** `Trip` → **LEFT JOIN** `ActivityExecution` | **todos** los viajes del día |
| `paradas_del_dia` ([dao.py:306](app/routers_api/activityexplorer/dao.py#L306)) | **`ActivityExecution`** → JOIN `Trip` | sólo los viajes **con actividad** |

**Un viaje sin `ActivityExecution` suma sus millas al total y no aparece en la
lista.** Eso es, exactamente, «los registros visibles no explican el total
acumulado».

Qué viajes son ésos, por diseño del dominio:

- los de regreso a casa (`HOME`), que cierran al llegar y nunca abren actividad;
- los **interrumpidos** por `End Work Anyway`, que no fabrican llegada;
- los que llegaron y cuya parada nunca se inició.

### Doble conteo por JOIN · `DESCARTADO` con evidencia de esquema

La sospecha era razonable y **no se sostiene**. Consulta de solo lectura a
`pg_index`:

```
uq_activity_execution_trip   UNIQUE  (trip_id)
uq_trip_mileage_trip         UNIQUE  (trip_id, company_id)
```

Con ambas relaciones a lo sumo 1:1, el encadenamiento
`WorkSession ⋈ Trip ⋈ ActivityExecution ⋈ TripMileage` produce **exactamente una
fila por viaje**. Ni `sum(metros)` ni el conteo pueden duplicar.

**La discrepancia no es por duplicación. Es por asimetría de conjuntos.**

---

## 1 · Tabla de conciliación

La estructura pedida, con la aritmética del caso. **Los identificadores quedan
pendientes de ejecutar las consultas en el entorno de las capturas** (§5).

| WorkSession | Trip | Propósito | TripMileage | Millas | ActivityExecution | ¿Visible en el detalle? |
|---|---|---|---|---|---|---|
| WS-A (`session_date` 08/10) | T-1 | `recruiting` | `calculated` | **62,5** | sí, terminada | **Sí** |
| WS-? | T-2 | `office` | `pending_calculation` | **0,0** + pending | sí, `in_progress` | **Sí** |
| **?** | **?** | **sin actividad** | `calculated` | **≈ 63,0** | **ninguna** | **No** ← |
| | | | **Total consolidado** | **125,5** | **2 visibles** | |

```
125,5  total que muestra el consolidado
− 62,5  recruiting (visible)
−  0,0  office (visible, pendiente de cálculo)
───────
  63,0  millas de uno o más viajes SIN actividad asociada
```

Las 63,0 millas **no son un error de suma**: son viajes reales cuyo kilometraje
está calculado y que el detalle no puede mostrar porque su consulta parte de
`ActivityExecution`.

**Clasificación:** la mecánica es `CONFIRMED`; la atribución de esas 63,0 millas
a viajes concretos es `PENDING VALIDATION` hasta ejecutar §5.

---

## 2 · WorkSessions

**No se puede afirmar sin consultar el entorno.** La captura de Today del día 7
mostraba dos jornadas para esa supervisora —una cerrada a las 6:30 y otra
abierta a las 10:58—, y el consolidado de 125,5 mi es compatible con que el día
8 tenga también dos jornadas.

Lo que sí está establecido, y responde a la instrucción de no suponer:

- **`pending` no implica jornada sin cerrar.** `mileage_pending` depende sólo de
  `TripMileage.state = 'pending_calculation'`, que es independiente del estado
  de la jornada. Un viaje de una jornada cerrada puede estar pendiente, y una
  jornada abierta puede no tener nada pendiente.
- El Explorer **agrupa por `WorkSession.session_date`**, así que incluye todas
  las jornadas del día 8, estén abiertas o cerradas.
- Una jornada **abierta del día 7** no entraría en el día 8: su `session_date`
  sigue siendo el 7. Es el riesgo que documenta el diagnóstico de jornadas sin
  cerrar, y **no** explicaría estas 63,0 millas en el día 8.

La consulta 2 de §5 lo resuelve en segundos.

---

## 3 · Métricas de actividad

Tres números que miden tres cosas distintas, y la pantalla no lo dice.

### `2 activities`

`activities=len(paradas)` — el número de `ActivityExecution` del día, es decir
**el tamaño de la lista visible**. No cuenta viajes. Es coherente con lo que se
ve, y por eso no delata que falten millas.

### `0m + activity time`

Dos partes, de dos campos distintos:

- **`0m`** ← `activity_seconds`, que suma `_duracion_segundos()`
  ([dao.py:153](app/routers_api/activityexplorer/dao.py#L153)):

  ```python
  case((ActivityExecution.ended_at.is_not(None),
        extract("epoch", ended_at - started_at)), else_=0)
  ```

  **Sólo las actividades terminadas aportan.** Una `in_progress` aporta cero a
  propósito: presentarla como de duración cero sería afirmar que no duró nada.

- **`+`** ← `has_open_activity`, verdadero porque *Office* está `in_progress`.
  Es el mismo recurso tipográfico que `+ pending`: «hay algo abierto que este
  número todavía no cuenta».

Que `0m` conviva con una actividad terminada (*Recruiting*) significa que su
duración fue inferior al redondeo: `ended_at − started_at` de pocos segundos.
Operativamente, llegar y completar la parada de inmediato.

### `Activity span` de Recruiting: 6h 08m

**No es la duración de la actividad.** Es
[`spanBetween(a.trip_started_at, a.ended_at)`](app/components/react/features/RouteActivityExplorer/ui/ExplorerActivityCards.tsx#L72):
desde que **salió el viaje** hasta que **terminó la actividad**. Incluye el
trayecto.

Las tres magnitudes, separadas:

| Concepto | Fórmula | En este caso |
|---|---|---|
| Duración del viaje | `arrived_at − trip_started_at` | parte de las 6h 08m |
| Tiempo en destino | `ended_at − arrived_at` | el resto |
| **Duración de la actividad** | `ended_at − started_at` de `ActivityExecution` | ≈ 0, de ahí `0m` |
| **Activity span** | `ended_at − trip_started_at` | **6h 08m** |

**`6h 08m` de span con `0m` de activity time es correcto según las fórmulas y
engañoso en pantalla.** Nada dice que una incluye el viaje y la otra no.

---

## 4 · Today vs User Activity

### Tras H-2, los totales coinciden

Las dos pantallas usan el **mismo conjunto**: todos los viajes de todas las
jornadas cuya `session_date` es el día consultado. Ninguna de las dos filtra por
existencia de actividad al sumar millas.

| | Today (tras H-2) | User Activity |
|---|---|---|
| Jornadas | todas las de `session_date` | todas las de `session_date` |
| Millas | suma de todos los viajes | suma de todos los viajes |
| Actividades | `count(ActivityExecution)` | `len(paradas)` |

**La discrepancia que motivó esta investigación —Today 62,5 frente a User
Activity 125,5— es la que H-2 corrige.** Antes, Today partía las millas entre
dos filas y mostraba una; el Explorer ya sumaba el día completo. Con H-2
desplegado, Today dirá también **125,5**.

### Lo que H-2 no toca, y queda abierto

La inconsistencia **interna** de User Activity: su propio total no cuadra con su
propia lista. H-2 modificó `live/dao.py`; no tocó `activityexplorer/`.

### Diferencia legítima de definición

Una sola, y conviene no «corregirla»: `activities` cuenta **paradas con
actividad registrada**, no viajes. Un día con cinco viajes y dos paradas tiene
dos actividades. Es correcto.

---

## 5 · Consultas de solo lectura · `PENDING VALIDATION`

**No tengo acceso al entorno de las capturas.** Las consultas no exponen nombres
ni correos y se ejecutan desde la consola del componente.

```sql
-- 1 · CONCILIACIÓN: un renglón por viaje del día. La suma de `millas`
--     tiene que dar exactamente el total del consolidado.
SELECT ws.id   AS work_session_id,
       ws.session_date,
       ws.status                                   AS ws_status,
       t.id    AS trip_id,
       t.status                                    AS trip_status,
       t.current_purpose,
       tm.state                                    AS mileage_state,
       ROUND(COALESCE(tm.total_meters, 0) / 1609.344, 1) AS millas,
       ae.id   AS activity_execution_id,
       ae.status                                   AS activity_status,
       (ae.id IS NOT NULL)                         AS visible_en_el_detalle
FROM work_session ws
JOIN trip t           ON t.work_session_id = ws.id
                     AND t.company_id = ws.company_id
LEFT JOIN trip_mileage tm      ON tm.trip_id = t.id AND tm.company_id = t.company_id
LEFT JOIN activity_execution ae ON ae.trip_id = t.id AND ae.company_id = t.company_id
WHERE ws.company_id   = :company_id
  AND ws.user_id      = :user_id
  AND ws.session_date = DATE '2026-10-08'
ORDER BY ws.id, t.sequence;

-- 2 · ¿Cuántas jornadas tiene ese día, y hay alguna abierta de días previos?
SELECT id, session_date, status, started_at, ended_at,
       (CURRENT_DATE - session_date) AS dias
FROM work_session
WHERE company_id = :company_id AND user_id = :user_id
  AND (session_date = DATE '2026-10-08' OR status = 'active')
ORDER BY session_date, started_at;

-- 3 · LA PRUEBA DIRECTA: millas de viajes SIN actividad.
--     Si devuelve ≈ 63.0, la causa raíz queda confirmada con datos.
SELECT COUNT(*) AS viajes_sin_actividad,
       ROUND(SUM(COALESCE(tm.total_meters, 0)) / 1609.344, 1) AS millas_invisibles
FROM work_session ws
JOIN trip t ON t.work_session_id = ws.id AND t.company_id = ws.company_id
LEFT JOIN trip_mileage tm       ON tm.trip_id = t.id AND tm.company_id = t.company_id
LEFT JOIN activity_execution ae ON ae.trip_id = t.id AND ae.company_id = t.company_id
WHERE ws.company_id   = :company_id
  AND ws.user_id      = :user_id
  AND ws.session_date = DATE '2026-10-08'
  AND ae.id IS NULL;

-- 4 · Duración real de cada actividad, para contrastar `0m` y el span.
SELECT ae.id, ae.status, ae.started_at, ae.ended_at,
       EXTRACT(EPOCH FROM (ae.ended_at - ae.started_at))    AS segundos_actividad,
       EXTRACT(EPOCH FROM (ae.ended_at - t.started_at))     AS segundos_span,
       t.started_at AS trip_started_at, t.arrived_at
FROM activity_execution ae
JOIN trip t          ON t.id = ae.trip_id AND t.company_id = ae.company_id
JOIN work_session ws ON ws.id = ae.work_session_id AND ws.company_id = ae.company_id
WHERE ws.company_id = :company_id AND ws.user_id = :user_id
  AND ws.session_date = DATE '2026-10-08'
ORDER BY ae.started_at;
```

**La consulta 3 es la decisiva.** Si devuelve cerca de 63,0 millas, la causa
raíz pasa de `CONFIRMED por código` a `CONFIRMED con datos`. Si devuelve 0, hay
una segunda causa y este documento no la ha encontrado.

### Las consultas están ejecutadas y validadas, en el entorno local

No en el de las capturas, pero sí comprobadas: corren sin error y **el mecanismo
aparece**. Sobre los datos de prueba de hoy:

```
18 viajes en el día · 14 visibles en el detalle · 4 invisibles
millas invisibles: 0,0 mi
```

**Cuatro de dieciocho viajes no aparecerían en la lista.** Sus millas son 0,0
sólo porque en el entorno de pruebas no se les escribió un kilometraje
calculado; con cifra, esas millas habrían entrado en el total y no en el
detalle, que es exactamente el caso reportado.

Esto confirma la **existencia del mecanismo** con datos reales de ejecución. Lo
que falta es su **magnitud** en producción, y la da la consulta 3.

---

## 6 · Expected vs Implemented

| | Esperado | Implementado | Veredicto |
|---|---|---|---|
| Total del día | suma de todos los viajes | **igual** | Conforme |
| Lista de actividades | lo que explica el total | sólo viajes con actividad | **Divergente** |
| Relación total ↔ lista | reconciliable | **no reconciliable** | **Divergente** |
| `activities` | nº de paradas | nº de paradas | Conforme |
| `activity time` | tiempo de actividad | tiempo de actividades **terminadas** | Conforme, mal rotulado |
| `activity span` | ¿duración de la actividad? | **viaje + destino** | **Ambiguo** |
| Today ↔ User Activity | mismos totales | coincidirán **tras H-2** | Corregido, sin desplegar |

---

## 7 · Componentes que originan la inconsistencia

| Componente | Papel |
|---|---|
| [`router.py:117-124`](app/routers_api/activityexplorer/router.py#L117) | **el origen**: arma un resumen con dos fuentes |
| [`dao.py:215` `agregados_por_dia`](app/routers_api/activityexplorer/dao.py#L215) | correcto; incluye todos los viajes |
| [`dao.py:306` `paradas_del_dia`](app/routers_api/activityexplorer/dao.py#L306) | correcto; parte de `ActivityExecution` |
| [`ExplorerActivityCards.tsx:72`](app/components/react/features/RouteActivityExplorer/ui/ExplorerActivityCards.tsx#L72) | rotula como *activity span* algo que incluye el viaje |

**Ninguna de las dos consultas está mal por separado.** Lo que falla es
presentarlas como si describieran el mismo conjunto.

---

## 8 · Corrección mínima propuesta

Reutilizando componentes existentes. **No implementada.**

### R-1 · Hacer visibles los viajes sin parada *(resuelve la causa)*

Que `paradas_del_dia` incluya también los viajes sin `ActivityExecution`
—cambiando su origen a `Trip` con `LEFT JOIN` a `ActivityExecution`— y que la
tarjeta los dibuje como lo que son: un trayecto sin parada registrada, con sus
millas y sin campos de actividad.

- **Reutiliza** `ExplorerActivityCards` y el contrato `ExplorerActivity`, con
  campos que ya son opcionales.
- **Impacto de API:** aditivo. **Migración:** ninguna.
- **Riesgo:** medio — cambia el conjunto que devuelve el endpoint, y el contador
  `activities` tendría que seguir contando **paradas**, no filas, para no
  romper su significado.
- **Esfuerzo:** ≈ 3,4 h.

### R-2 · Rotular las magnitudes de tiempo *(resuelve la ambigüedad)*

Nombrar en la tarjeta lo que cada número mide: el span incluye el trayecto, el
activity time no. Sin cambiar ninguna fórmula.

- Sólo presentación. **API:** sin cambios. **Esfuerzo:** ≈ 0,8 h.

### R-3 · Alternativa más barata a R-1, si el PO prefiere no tocar la lista

Añadir al resumen una línea explícita: «63,0 mi en N trayectos sin parada
registrada». El total deja de ser inexplicable sin cambiar el conjunto de la
lista.

- **Esfuerzo:** ≈ 1,6 h. Es la opción que recomiendo si hay prisa.

### Lo que **no** se propone

- Cambiar el total: **las 125,5 millas son correctas**. Son viajes reales con
  kilometraje calculado.
- Excluir del total los viajes sin actividad: ocultaría kilometraje real.
- Tocar `agregados_por_dia` ni `paradas_del_dia` por separado: cada una es
  correcta en su propio dominio.

---

## 9 · Impacto sobre H-2

**Ninguno.** H-2 modificó `app/routers_api/live/dao.py` y la selección en
`RouteTodayLivePage.tsx`. No tocó `activityexplorer/` en ninguna línea.

Y en la dirección contraria: **H-2 mejora la conciliación**. Antes, Today
partía las millas del día entre dos filas y el panel mostraba una; el Explorer
ya sumaba el día completo. Con H-2 las dos pantallas parten del mismo conjunto y
sus totales coinciden.

Ninguna corrección de §8 requiere revisar H-2.

---

## 10 · Pruebas necesarias

Para R-1 o R-3, cuando se autoricen:

1. **Integración · un viaje sin actividad.** Un día con un viaje `HOME`
   calculado y uno operativo con parada: el total y lo visible deben
   reconciliar. **Es la prueba que reproduce este caso.**
2. **Integración · viaje interrumpido.** `End Work Anyway` deja un viaje sin
   actividad y con millas; mismo criterio.
3. **Integración · el contador no cambia de significado.** `activities` debe
   seguir contando paradas, no trayectos, aunque la lista crezca.
4. **Integración · control de no regresión del total.** Las millas no cambian
   con ninguna de las correcciones: sólo cambia lo que se muestra.
5. **E2E** sobre la pantalla, que es donde el administrador suma con la vista.
6. **Verificación contra el código anterior**, como en H-2: la prueba 1 debe
   fallar hoy.

Esfuerzo de pruebas incluido en las estimaciones de §8.

---

## Limitaciones

1. **No se consultó el entorno de las capturas.** La mecánica está confirmada
   por código y esquema; la atribución de las 63,0 millas a viajes concretos es
   `PENDING VALIDATION` hasta ejecutar §5.
2. **La aritmética de §1 es deductiva**: 125,5 − 62,5 − 0,0 = 63,0. Encaja con
   la causa raíz, pero no se ha contrastado contra los registros.
3. **La explicación de `0m` con *Recruiting* terminada** —duración por debajo
   del redondeo— es la lectura que hacen las fórmulas, no un hecho verificado.
   La consulta 4 lo confirma o lo desmiente.
4. **No se ha comprobado si hay jornadas del día 7 todavía abiertas** para esa
   supervisora. No explicarían estas millas, pero cambian el panorama.
5. **No se ejecutó ninguna prueba** en este diagnóstico.
