# CER Route · Diagnóstico: kilometraje pendiente y jornadas sin cerrar

**Documento 001** · 8 de octubre de 2026
**Tipo:** investigación de solo lectura · **Estado:** `DIAGNOSTIC ONLY — NOT IMPLEMENTED`

> No se modificó código, no se ejecutaron cierres ni ajustes, y no se tocó
> ningún dato. H-2 queda exactamente como se entregó.

---

## Respuesta corta

**No, las jornadas abiertas de días anteriores no producen el `+ pending` de
Today.** Son dos asuntos independientes y la evidencia lo demuestra: el
indicador sólo mira viajes de jornadas cuya `session_date` es **hoy**.

Pero la investigación encontró algo peor que lo que se buscaba. Una jornada
abierta de un día anterior **no afecta a Today: desaparece de él**, y con ella
todo el trabajo que se haga encima. El supervisor aparece como `Not started`
mientras conduce.

---

# A · Kilometraje pendiente

## A.1 · Qué activa `mileage_pending` · `CONFIRMED`

Un único estado, y no los demás
([`mileage/read.py:94-106`](app/routers_api/mileage/read.py#L94)):

```python
def pendientes():
    return case((TripMileage.state == MileageState.PENDING_CALCULATION.value, 1), else_=0)
```

`mileage_pending` es verdadero cuando **al menos un viaje** de las jornadas de
hoy tiene su kilometraje en `pending_calculation`. Los cuatro estados posibles:

| Estado | ¿`+ pending`? | Significa |
|---|---|---|
| `pending_calculation` | **sí** | transitorio: queda un camino automático |
| `calculated` | no | tiene cifra |
| `not_calculable` | no | terminal: faltó evidencia de ubicación |
| `calculation_failed` | no | terminal: el proveedor no pudo |

Los dos terminales **no** son pendientes: su respuesta es definitiva aunque no
sea un número, y se informan aparte con `mileage_unresolved`.

## A.2 · Sincronización offline ≠ cálculo de kilometraje · `CONFIRMED`

Son dos limbos distintos y no se tocan:

| | Dónde vive | Qué significa | ¿Afecta a `+ pending`? |
|---|---|---|---|
| Cola offline | IndexedDB, en el teléfono | la acción no ha llegado al servidor | **No.** Sin acción no hay viaje, y sin viaje no hay fila de kilometraje |
| `pending_calculation` | `trip_mileage`, en la base | el viaje llegó y falta calcular su distancia | sí |

Una acción encolada es **invisible** para Today hasta que sincroniza. El
indicador no puede reflejarla.

## A.3 · Qué registros lo mantienen activo y qué lo apaga · `CONFIRMED`

**Cuándo nace la fila:** sólo cuando el viaje pasa a `ARRIVED` o `INTERRUPTED`,
dentro de la misma transacción
([`mileage/service.py:245-252`](app/routers_api/mileage/service.py#L245)). Un
viaje en `planning` o `in_transit` **no tiene fila**: ni suma millas ni aparece
como pendiente.

**Qué lo apaga:** el barrido periódico
([`mileage/jobs.py:35`](app/routers_api/mileage/jobs.py#L35)), por una de dos
vías: calcula con éxito → `calculated`, o agota el reintento acotado →
`calculation_failed` / `not_calculable`.

**Por qué puede durar horas:** el reintento usa espera exponencial,
`base · 2^(n-1)`, con `max_attempts = 10`. En conjunto son unas **8,5 horas**
antes de terminalizar. Durante toda esa ventana el viaje está `pending` y el
indicador encendido, **aunque el cálculo esté fallando desde el primer intento**.

Observado en el entorno local de desarrollo —no en producción— como ilustración
del mecanismo:

```
trip=457  ws=351  fecha=2026-10-08  intentos=8  próximo=21:16Z
trip=461  ws=348  fecha=2026-10-08  intentos=0  próximo=19:13Z
```

El primero lleva 8 de 10 intentos y el siguiente está a más de dos horas vista.
**Ése es el aspecto del `+ pending` persistente.**

## A.4 · ¿Puede un viaje de una jornada anterior encender el indicador? · `CONFIRMED: NO`

La consulta de millaje de Today filtra por las jornadas del día:

```python
Trip.work_session_id.in_(sesiones)
```

y `sesiones` sale del `LEFT JOIN` con `WorkSession.session_date == dia`
([`live/dao.py:114`](app/routers_api/live/dao.py#L114)). Un viaje colgado de una
jornada de ayer **no entra en la consulta**.

El riesgo real es el inverso, y es el hallazgo de §B.

## A.5 · El caso observado · `PENDING VALIDATION`

**No se ejecutó contra producción: no tengo acceso a esa base.** Entregar un
identificador inventado sería peor que no entregarlo.

Las consultas son de solo lectura, no exponen nombres ni correos, y están
listas para ejecutar desde la consola del componente:

```sql
-- 1. ¿De dónde sale el `+ pending` de un supervisor hoy?
SELECT tm.trip_id, tm.state, tm.attempt_count, tm.next_attempt_at,
       tm.terminal_reason, t.status AS trip_status,
       ws.id AS work_session_id, ws.session_date, ws.status AS ws_status
FROM trip_mileage tm
JOIN trip t          ON t.id = tm.trip_id
JOIN work_session ws ON ws.id = t.work_session_id
WHERE ws.company_id = :company_id
  AND ws.user_id    = :user_id
  AND ws.session_date = :dia
ORDER BY tm.next_attempt_at;

-- 2. ¿Tiene jornadas abiertas de días anteriores?
SELECT id, session_date, status, started_at, ended_at,
       (CURRENT_DATE - session_date) AS dias_abierta
FROM work_session
WHERE company_id = :company_id AND status = 'active'
ORDER BY session_date;

-- 3. Panorama de toda la compañía, para dimensionar antes de decidir
SELECT ws.session_date, tm.state, count(*) AS n
FROM trip_mileage tm
JOIN trip t          ON t.id = tm.trip_id
JOIN work_session ws ON ws.id = t.work_session_id
WHERE ws.company_id = :company_id
  AND ws.session_date >= CURRENT_DATE - 14
GROUP BY ws.session_date, tm.state
ORDER BY ws.session_date DESC;
```

La consulta 2 es la que importa: **si devuelve filas, el problema de §B existe
en producción hoy.**

## A.6 · Excepciones de odómetro y viajes incompletos · `CONFIRMED`

| Caso | ¿Mantiene kilometraje pendiente? |
|---|---|
| Excepción de odómetro de inicio o cierre | **No.** El kilometraje no referencia el odómetro en ninguna línea; son dominios independientes |
| Viaje en `planning` o `in_transit` | **No.** No tiene fila de kilometraje — pero tampoco suma millas nunca |
| Viaje `arrived` sin resolver la parada | **Sí**, hasta que el barrido lo calcule o lo terminalice |

El segundo caso merece atención: un viaje que se queda en tránsito para siempre
**no enciende ningún indicador y no aporta millas**. Desaparece en silencio, que
es justo lo que `mileage_unresolved` se construyó para evitar en el otro caso.

---

# B · Jornadas sin cerrar

## B.1 · Cómo se determina que sigue abierta · `CONFIRMED`

```python
select(WorkSession).where(
    WorkSession.company_id == company_id,
    WorkSession.user_id == user_id,
    WorkSession.status == WorkSessionStatus.ACTIVE.value,
)
```

[`worksessions/dao.py:36-51`](app/routers_api/worksessions/dao.py#L36). **No hay
filtro de fecha.** Una jornada abierta hace tres días sigue siendo «la jornada
vigente», y su docstring lo dice: *«Es la fuente de ¿está trabajando ahora?»*.

## B.2 · Qué ocurre si no se ejecuta End Work y vuelve al día siguiente · `CONFIRMED`

```python
existente = await WorkSessionsDAO.find_active_for_user(...)
if existente is not None:
    return existente, False
```

[`worksessions/service.py:162-165`](app/routers_api/worksessions/service.py#L162).

`Start Work` **devuelve la jornada de ayer** y la trata como un `Start Work`
repetido. No crea una jornada nueva, no avisa y no compara fechas. El
comportamiento es correcto para el caso que se diseñó —pulsar dos veces el
botón— y silencioso para éste.

**Las consecuencias, en cadena:**

1. `session_date` sigue siendo **el de ayer**, y nunca se recalcula.
2. Today filtra por `session_date == hoy`, así que esa jornada **no aparece**.
3. El supervisor sale como **`Not started`** mientras conduce
   ([`live/dao.py:272`](app/routers_api/live/dao.py#L272): sin fila de jornada,
   `estado = "not_started"`).
4. Los viajes de hoy se cuelgan de la jornada de ayer y suman **al Today de
   ayer**, que ya nadie mira.
5. Sus millas de hoy no aparecen en ninguna pantalla del día de hoy.

## B.3 · ¿Puede continuar una jornada anterior accidentalmente? · `CONFIRMED: SÍ`

Es el camino por defecto, y no requiere ningún error del supervisor: basta con
no pulsar `End Work` y volver a abrir la aplicación. **Nada en la interfaz
distingue una jornada de hoy de una de anteayer.**

## B.4 · Mecanismos de recuperación o cierre administrativo · `CONFIRMED: NO EXISTEN`

Búsqueda sobre el dominio de jornadas y el barrido:

```
force_end | auto_close | expire | stale | cierre administrativo
→ sin resultados
```

**No hay cierre administrativo, ni caducidad automática, ni ajuste, ni
herramienta de recuperación.** La única forma de cerrar una jornada es que su
propio supervisor pulse `End Work` — y eso exige, además, resolver la parada
pendiente y la lectura de odómetro de cierre.

El barrido periódico sólo toca ventanas de ubicación y kilometraje; **no mira
las jornadas**.

## B.5 · Jornadas legítimas que cruzan medianoche · `CONFIRMED`

Funcionan correctamente. `session_date` se congela al abrir
([`worksessions/models.py:69`](app/routers_api/worksessions/models.py#L69)) y un
turno de noche pertenece al día en que empezó, que es la decisión correcta
(D-10).

**El problema es que el sistema no puede distinguirlas de un olvido.** Una
jornada abierta a las 23:00 que cierra a las 02:00 y otra abierta ayer que nadie
cerró se ven exactamente igual: `status = 'active'`, `session_date` de ayer.

## B.6 · Efecto sobre Today · `CONFIRMED`

| | Efecto |
|---|---|
| Selección de fecha | **ninguno**: `business_day()` no mira el estado de las jornadas |
| Métricas de hoy | **ninguno**: el filtro por `session_date` las excluye |
| Fila del supervisor | aparece como `Not started` aunque esté trabajando |
| Métricas de ayer | **sí**: siguen creciendo con el trabajo de hoy |

---

# C · Integridad de datos

| Escenario | Veredicto |
|---|---|
| Jornada abierta varios días | **Íntegro pero engañoso.** Las claves foráneas se mantienen; lo que falla es la interpretación: el trabajo se atribuye a un día que no es |
| Viajes sin kilometraje calculado | **Íntegro.** Los cuatro estados son explícitos y ninguno finge una cifra |
| Acciones offline sin sincronizar | **Íntegro.** Nada se escribe hasta que llegan, y llegan con su hora de origen |
| Intento de iniciar jornada nueva | **Íntegro, y ahí está el defecto:** devuelve la anterior en vez de crear una |
| Excepción de odómetro | **Íntegro.** Dominio independiente del kilometraje |

**No se encontró ninguna corrupción, ni huérfanos, ni relaciones rotas.** El
índice único parcial `uq_work_session_one_active` garantiza que no puede haber
dos jornadas activas por persona, y es precisamente lo que produce el efecto de
§B.2: como no puede crear otra, devuelve la que hay.

## Riesgos de auditoría

1. **Atribución temporal incorrecta.** El trabajo de hoy queda registrado bajo
   la fecha de ayer. No es un dato corrupto: es un dato correcto mal fechado, y
   eso es más difícil de detectar después.
2. **Horas de jornada infladas.** Una jornada abierta 3 días produce una
   duración de 72 horas si alguien la calcula como `ended_at - started_at`. Es
   un dato laboral.
3. **Kilometraje atribuido al día equivocado**, con el mismo efecto sobre
   cualquier informe por fecha.
4. **Ninguna de las tres deja rastro de que algo fue anómalo.** No hay evento de
   auditoría para «jornada continuada al día siguiente», porque el sistema no
   sabe que lo es.

---

# D · GAPs y decisiones de producto

| | Asunto | Tipo |
|---|---|---|
| **G-1** | ¿Qué debe pasar cuando se abre la aplicación con una jornada de un día anterior? | `DECISION REQUIRED` |
| **G-2** | ¿Existe cierre administrativo? Hoy no, y una jornada olvidada **no tiene salida** salvo que su supervisor la cierre | `GAP` |
| **G-3** | ¿Un turno de noche es legítimo en esta operación? Determina si G-1 puede automatizarse o debe preguntar | `DECISION REQUIRED` |
| **G-4** | ¿Debe Today mostrar al supervisor con jornada de otro día, en vez de `Not started`? | `DECISION REQUIRED` |
| **G-5** | ¿El `+ pending` debe distinguir «calculando» de «reintentando desde hace horas»? | `DECISION REQUIRED` |

Sobre G-1, las opciones y lo que implican:

- **(a) Preguntar al supervisor** al detectar una jornada de otro día: «¿sigues
  en la jornada de ayer o empiezas una nueva?». Respeta el turno de noche y no
  decide por él.
- **(b) Cerrar automáticamente** la anterior y abrir una nueva. Escribe un
  `ended_at` que nadie observó — exactamente lo que la Opción B de C4 quería
  evitar y que el checkpoint del odómetro acaba de revertir.
- **(c) Avisar sin bloquear**: la pantalla dice «llevas abierta la jornada del
  día 6» y deja seguir.

Recomendación técnica: **(a) o (c)**. La (b) fabrica evidencia.

---

# E · Propuesta de corrección mínima

Reutilizando lo que ya existe, sin tocar H-2, interfaces, navegación,
kilometraje, históricos, sincronización ni permisos.

### E-1 · Hacer visible la jornada de otro día *(resuelve el síntoma, no la causa)*

Que `GET /api/worksessions/current` indique si la jornada vigente es de una
fecha anterior —un campo derivado de `session_date`, sin almacenar nada— y que
la pantalla del supervisor lo diga.

- Reutiliza: el endpoint y la pantalla actuales.
- API: **aditivo**. Migración: **ninguna**.
- Esfuerzo: **≈ 1,8 h**.

### E-2 · Decidir en `Start Work` *(resuelve la causa)* — depende de G-1

Si se elige (a), `Start Work` responde que hay una jornada de otro día abierta y
el cliente pregunta. **No se cierra nada automáticamente.**

- Reutiliza: `_session_date_from`, que ya calcula la fecha local.
- API: aditivo. Migración: ninguna.
- Esfuerzo: **≈ 3,2 h**.

### E-3 · Consulta de supervisión para CER *(no es producto)*

Las tres consultas de §A.5, documentadas donde el equipo pueda ejecutarlas.
Permite vigilar el problema mientras se decide G-1.

- Esfuerzo: **≈ 0,4 h**.

### E-4 · Distinguir «reintentando» de «calculando» — depende de G-5

El dato ya existe: `attempt_count` y `next_attempt_at`.

- Esfuerzo: **≈ 1,5 h**.

### Lo que **no** se propone

- Cerrar jornadas automáticamente (fabrica un `ended_at` falso).
- Tocar `business_day()` ni el filtro por `session_date`, que son correctos.
- Ninguna migración ni corrección sobre datos históricos: **cualquier
  reatribución de trabajo a otra fecha es una decisión de negocio**, no una
  corrección técnica, y ninguna evidencia de este diagnóstico la justifica.

---

# F · Checkpoints recomendados

| # | Unidad | Depende de | Esfuerzo | Verificable por |
|---|---|---|---|---|
| **P-1** | Consultas de supervisión y medición en producción | — | 0,4 h | ejecutarlas y ver si §B existe hoy |
| **P-2** | Avisar de la jornada de otro día | G-3 | 1,8 h | integración: jornada de ayer → la pantalla lo dice |
| **P-3** | Decisión en `Start Work` | G-1, P-2 | 3,2 h | integración: los tres caminos de la decisión |
| **P-4** | `+ pending` con contexto de reintento | G-5 | 1,5 h | integración sobre `attempt_count` |

**P-1 primero, y no es una formalidad:** dice si esto es un problema teórico o
está ocurriendo. En el entorno local **no hay ninguna jornada activa de días
anteriores**, de modo que el caso no está reproducido con datos reales.

Total P-1 a P-4: **≈ 6,9 h-agente**, con márgenes +10 % / +50 % aplicados.

---

# Limitaciones

1. **No se consultó producción.** §A.5 queda `PENDING VALIDATION` y las
   consultas se entregan sin ejecutar.
2. **Los datos de §A.3 son del entorno local** y provienen de ejecuciones de
   prueba de hoy. Ilustran el mecanismo del reintento; **no son evidencia de
   campo** y no describen la operación de CER.
3. **El caso concreto de Karina no se pudo identificar** sin acceso a esa base.
4. **No se ejecutó ninguna prueba** en este diagnóstico.
5. **No se midió** cuántas jornadas se quedan abiertas por semana en la
   operación real. Esa cifra decide la prioridad de G-1 y la da P-1.
