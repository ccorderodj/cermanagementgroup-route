# CER Route · Conciliación Today / User Activity — resultados

**Documento 002** · 8 de octubre de 2026 · continúa el 001
**Tipo:** ejecución de consultas de solo lectura · **Estado:** `RESULTS — NOT IMPLEMENTED`
**Caso:** supervisora K.A. (`user_id = 270`), 08/10/2026

> No se modificó código, interfaces, contratos ni datos históricos. R-1, R-2 y
> R-3 siguen sin implementar.

---

## 0 · En qué entorno se ejecutó, y por qué importa

**No es producción.** Es la copia local de `cerroute` (`DB_HOST = localhost`,
`DB_NAME = db-dev-cer-route`, compañía `cerroute`, `id = 1`). **Los datos son
reales**, no sembrados, y llegan hasta el 08/10/2026.

**La copia está desfasada respecto a las capturas.** Se demuestra con un dato
del propio resultado: los dos viajes no calculados tienen `next_attempt_at` a
las **19:13 y 19:14 UTC**, y aún figuran con `attempt_count = 0`. La copia se
tomó **antes de ese instante**; las capturas del Product Owner son posteriores.

### Corrección a los documentos 001 y al diagnóstico de jornadas

En ambos presenté estos registros como «datos de prueba de mi entorno local,
restos de las ejecuciones de hoy». **Es incorrecto.** La suite de pruebas usa
otra base (`cer_time_test`); ésta contiene datos reales de `cerroute`.

El efecto va a favor de la investigación —la evidencia era mejor de lo que
afirmé— pero la etiqueta era falsa y conviene rectificarla por escrito.

---

## 1 · Conciliación · `CONFIRMED con datos`

```
ws=347  trip=447  seq=1  recruiting  closed    calculated            62.5 mi  VISIBLE   ae=154 completed
ws=347  trip=460  seq=2  home        closed    pending_calculation    0.0 mi  invisible ae=—
ws=347  trip=464  seq=3  office      arrived   pending_calculation    0.0 mi  invisible ae=—

TOTAL en esta copia = 62.5 mi
```

**Jornadas del día:**

| WorkSession | `session_date` | Estado | Inicio | Fin |
|---|---|---|---|---|
| 346 | 2026-10-08 | `ended` | 10:29:56 | 10:30:07 |
| 347 | 2026-10-08 | `active` | 11:32:39 | — |

La jornada 346 duró **11 segundos** y no tiene ningún viaje: es la fila
«Work Ended · 0.0 mi» que aparecía en la captura de Today. No hay ninguna
jornada activa de días anteriores para esta supervisora.

## 2 · Qué viajes componen las 125,5 millas

**Los tres viajes están identificados.** Dos de ellos no tienen
`ActivityExecution`:

| Trip | Propósito | Estado | `ActivityExecution` | ¿En el detalle? |
|---|---|---|---|---|
| **447** | `recruiting` | `closed` | 154, `completed` | **Sí** |
| **460** | **`home`** | `closed` | **ninguna** | **No** ← |
| **464** | `office` | `arrived` | ninguna *en esta copia* | — |

Cruzando con lo que muestran las capturas —*Recruiting* 62,5 mi y *Office* 0,0 mi
`In progress`, dos actividades—, la reconstrucción es:

```
  62,5 mi   trip 447 · recruiting · calculado · VISIBLE
+ 63,0 mi   trip 460 · home       · calculado después de esta copia · INVISIBLE
+  0,0 mi   trip 464 · office     · sigue pendiente · visible (su actividad se inició tras la copia)
──────────
 125,5 mi   total del consolidado · 2 actividades visibles
```

**El viaje que falta en el detalle es el regreso a casa (`trip 460`).** Es
exactamente el caso que el documento 001 describió como causa raíz: un viaje
`HOME` cierra al llegar y **nunca abre actividad**, así que suma millas y no
tiene parada que mostrar.

## 3 · ¿Son esas 63,0 millas las de ese viaje? · `PENDING VALIDATION`

**No se puede afirmar desde esta copia, y no lo voy a afirmar.** Aquí
`trip 460` aún está en `pending_calculation` con `attempt_count = 0`: su
kilometraje todavía no existía cuando se tomó la copia.

Lo que sí está establecido:

- es el **único** viaje de ese día con millas potenciales y sin actividad;
- su propósito, `home`, es el caso canónico de viaje sin parada;
- la aritmética cierra exactamente: 125,5 − 62,5 − 0,0 = 63,0.

Una consulta cierra el punto en el entorno de las capturas:

```sql
SELECT t.id, t.current_purpose, t.status,
       tm.state, tm.total_meters,
       ROUND(COALESCE(tm.total_meters,0)/1609.344, 1) AS millas,
       (SELECT count(*) FROM activity_execution ae WHERE ae.trip_id = t.id) AS actividades
FROM trip t
LEFT JOIN trip_mileage tm ON tm.trip_id = t.id AND tm.company_id = t.company_id
WHERE t.id IN (447, 460, 464);
```

**Si `trip 460` devuelve `calculated` con ≈ 63,0 millas y 0 actividades, la
causa raíz queda cerrada.** Si devuelve otra cosa, hay una segunda causa que
este análisis no ha encontrado, y conviene saberlo.

## 4 · Recruiting: Activity Span frente a Activity Time · `CONFIRMED con datos`

Los timestamps reales de `ae = 154`:

| Hito | Hora (UTC) |
|---|---|
| El viaje sale | 11:33:15 |
| Llega al destino | 14:58:18 |
| **Empieza** la actividad | 17:40:47 |
| **Termina** la actividad | 17:41:16 |

De ahí salen los tres números, y no miden lo mismo:

| Magnitud | Cálculo | Valor |
|---|---|---|
| Duración del viaje | 11:33:15 → 14:58:18 | **3h 25m** |
| Espera en destino antes de abrir la parada | 14:58:18 → 17:40:47 | **2h 42m** |
| **Duración de la actividad** | 17:40:47 → 17:41:16 | **29 segundos** |
| **Activity span** | 11:33:15 → 17:41:16 | **6h 08m** |

**El span de 6h 08m coincide exactamente con la captura, y los 29 segundos
redondean a `0m`.** Las dos cifras son correctas.

La explicación del documento 001 queda confirmada con datos: de esas 6h 08m,
**3h 25m son viaje y 2h 42m son espera en el destino**. Sólo 29 segundos son
actividad. La pantalla presenta las dos magnitudes juntas sin decir que una
contiene al viaje y la otra no.

## 5 · ¿Pueden las tarjetas representar un viaje sin actividad? · **Parcialmente**

Respuesta honesta: **la tarjeta sí; el contrato no, sin dos cambios.**

### Lo que ya funciona

`ExplorerActivityCards` dibuja casi todo desde campos del **viaje**, no de la
actividad: hora de salida, span, travel, millas y propósito. Y ya tolera la
ausencia de datos de actividad — `outcome_label || 'In progress'`,
`activity_labels` vacío, `spanBetween` devuelve `—` cuando falta un extremo.

### Lo que lo impide hoy

Dos campos **obligatorios** en el contrato
([`schemas.py:85-108`](app/routers_api/activityexplorer/schemas.py#L85)) que un
viaje sin actividad no puede rellenar:

```python
activity_execution_id: int    # no opcional
started_at: datetime          # no opcional — es el inicio de la ACTIVIDAD
```

Y uno de ellos es además la clave de render:
[`ExplorerActivityCards.tsx:57`](app/components/react/features/RouteActivityExplorer/ui/ExplorerActivityCards.tsx#L57)
usa `key={a.activity_execution_id}`.

### Lo que haría falta, y es poco

1. `activity_execution_id` y `started_at` → opcionales.
2. La clave de render → `trip_id`, que siempre existe y es único por fila.
3. La tarjeta sin actividad muestra `—` en *Activity* y nada en el resultado.

**No exige rediseñar ninguna interfaz.** Es relajar dos campos y cambiar una
clave.

### El contador de actividades · la advertencia que importa

```python
activities=len(paradas)
```

Si `paradas` pasara a incluir viajes sin actividad, **ese contador cambiaría de
significado en silencio**: pasaría a contar trayectos. La captura diría
«3 activities» cuando hubo dos.

**Cualquier implementación de R-1 debe calcular el contador aparte** —contando
sólo las filas con `activity_execution_id`— y tener una prueba que lo fije. Es
el riesgo concreto de esta corrección, y es el que el Product Owner pidió
verificar.

---

## 6 · Recomendación mínima ajustada

Con los datos en la mano, ajusto lo propuesto en el documento 001.

**Sigo recomendando R-1**, y ahora con una precisión que antes no tenía: el caso
no es raro ni marginal. **Todo viaje de regreso a casa cae en él**, y eso ocurre
casi todos los días en casi todas las jornadas. La magnitud de hoy —63 millas de
125,5, la mitad del día— sugiere que el total de User Activity ha sido
inexplicable de forma rutinaria, no excepcional.

**Alcance mínimo, en este orden:**

1. `paradas_del_dia` parte de `Trip` con `LEFT JOIN` a `ActivityExecution`.
2. `activity_execution_id` y `started_at` pasan a opcionales; la clave de render
   pasa a `trip_id`.
3. **El contador se calcula aparte**, contando sólo filas con actividad.
4. La tarjeta sin actividad dice lo que es: un trayecto sin parada registrada.

**Esfuerzo ajustado: ≈ 3,4 h**, igual que la estimación inicial. El trabajo
añadido del contador se compensa con que el análisis ya está hecho.

**R-2 (rotular los tiempos) sube de prioridad.** Los datos muestran por qué:
2h 42m de espera en destino están incluidas en un número llamado *activity
span*. No es un matiz cosmético — es tiempo operativo que hoy nadie puede
distinguir.

**R-3 (sólo una línea en el resumen) deja de ser suficiente.** Con el viaje
invisible siendo la mitad del kilometraje del día, decir «63 mi en trayectos sin
parada» sin poder verlos deja la pregunta a medias.

---

## 7 · Lo que no se hizo

- No se ejecutó nada en el entorno de las capturas: no tengo acceso a esa base,
  y obtenerlo exigiría credenciales de producción que no debo materializar.
- No se modificó ni un registro. Las cuatro consultas son `SELECT`.
- No se implementó R-1, R-2 ni R-3.
- **No se confirmó el valor de `trip 460`** (§3). Es el único dato que falta
  para cerrar la causa raíz, y requiere una consulta en el entorno correcto.
