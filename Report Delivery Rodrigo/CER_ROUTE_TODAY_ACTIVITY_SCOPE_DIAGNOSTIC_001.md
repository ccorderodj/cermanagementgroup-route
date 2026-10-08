# CER Route · Diagnóstico Today / Activity / Scope

**Documento 001** · 8 de octubre de 2026
**Tipo:** investigación de solo lectura · **Estado:** `DIAGNOSTIC ONLY — NOT IMPLEMENTED`
**Alcance:** `/admin/route/today`, `/admin/route/activity`, `/route/activity`

> No se ha escrito código, no se han creado migraciones y no se ha modificado
> ninguna funcionalidad. Todo lo que sigue sale de leer el repositorio y los
> contratos de datos, con referencia de archivo y línea.

---

## Resumen para quien decide

Se investigaron seis frentes. **Los problemas reportados no comparten una única
causa**, y tratarlos como un solo «bug de sincronización» llevaría a una
corrección equivocada. Son **cuatro asuntos independientes**:

| | Asunto | Naturaleza |
|---|---|---|
| 1 | Today muestra el detalle equivocado con varias jornadas | **Defecto** · `CONFIRMED` |
| 2 | *Current / Last Activity* muestra el propósito del viaje, no la actividad | **Desviación de contrato** · `CONFIRMED` |
| 3 | `/route/activity` no está construido | **Alcance pendiente** · `GAP`, declarado |
| 4 | El filtro de supervisor no aparece en el móvil del admin | **Diseño aprobado** · `DECISION REQUIRED` |

Y una hipótesis del planteamiento **queda descartada con evidencia**: el
Activity Explorer de administración **no excluye** los registros en curso.

---

# A · AS-BUILT

## A.1 · Today / Live

| Pieza | Ubicación |
|---|---|
| Página (servidor) | [`routers_pages/admin/route/router.py:60`](app/routers_pages/admin/route/router.py#L60) · `name="RouteTodayLivePage"` |
| Capacidad de página | `route.live.read` |
| Endpoint | [`routers_api/live/router.py`](app/routers_api/live/router.py) · `GET /api/live/today` |
| DAO | [`routers_api/live/dao.py`](app/routers_api/live/dao.py) |
| Contrato | [`routers_api/live/schemas.py:41`](app/routers_api/live/schemas.py#L41) · `LiveSupervisor` |
| Página (cliente) | [`RouteTodayLivePage.tsx`](app/components/react/pages/RouteTodayLivePage/ui/RouteTodayLivePage.tsx) |
| Componentes | `features/RouteLive/` · `LiveSupervisorTable`, `LiveSupervisorDetail`, `LiveMobileList`, `LiveMobileDetail` |

### Cómo se genera la lista

[`live/dao.py:109-119`](app/routers_api/live/dao.py#L109) parte de
`SupervisorProfile` y hace `outerjoin` a `WorkSession`:

```python
.outerjoin(
    WorkSession,
    (WorkSession.user_id == SupervisorProfile.user_id)
    & (WorkSession.company_id == SupervisorProfile.company_id)
    & (WorkSession.session_date == dia),
)
```

**El join no está limitado a una jornada.** Produce una fila por combinación
perfil × jornada del día.

### Cómo se identifica cada fila

[`live/schemas.py:53-55`](app/routers_api/live/schemas.py#L53): el contrato
expone `supervisor_profile_id` y `user_id`. **No expone `work_session_id`.**
Dos jornadas del mismo supervisor producen dos filas con **identificadores
idénticos**.

### Cómo se resuelve el detalle

[`RouteTodayLivePage.tsx:98`](app/components/react/pages/RouteTodayLivePage/ui/RouteTodayLivePage.tsx#L98):

```ts
const elegido = supervisores.find((s) => s.user_id === seleccionado)
    ?? supervisores[0] ?? null;
```

`Array.find` devuelve **la primera** coincidencia. El estado de selección
(`seleccionado`, línea 35) guarda un `user_id`.

### Cómo se calcula cada dato

| Dato | Origen | Línea |
|---|---|---|
| `status` | cascada: `ended` → `activity` → `route` → `working` → `not_started` | [`dao.py:271-285`](app/routers_api/live/dao.py#L271) |
| `since` | `ended_at` \| `actividad.started_at` \| `viaje.started_at` \| `viaje.arrived_at` \| `sesion.started_at` | ídem |
| `official_miles` | millaje oficial **de esa jornada** | `dao.py` §5 |
| `activities_today` | `count(ActivityExecution)` **de esa jornada** | [`dao.py:188-200`](app/routers_api/live/dao.py#L188) |
| `activity_label` | `Trip.current_purpose` del viaje vigente | [`dao.py:299`](app/routers_api/live/dao.py#L299) |
| `activity_reference` | `Trip.current_context_reference` | [`dao.py:300`](app/routers_api/live/dao.py#L300) |

### De dónde sale *Current / Last Activity*

```python
"activity_label": viaje.current_purpose if viaje is not None else None,
```

Y `viaje` ([`dao.py:143-160`](app/routers_api/live/dao.py#L143)) es el viaje de
mayor `sequence` cuyo estado sea `in_transit` **o** `arrived`.

**No procede de `ActivityExecution`.** `ActivityExecution` se consulta
([`dao.py:164-184`](app/routers_api/live/dao.py#L164)) **sólo** para decidir si
el estado es `activity`; ni su identificador ni su contenido llegan al contrato.

### Tratamiento de estados de actividad

| Estado | Uso en Today |
|---|---|
| `IN_PROGRESS` | decide `status = "activity"` y `since` |
| `COMPLETED` | sólo suma a `activities_today` |
| `LEFT` | sólo suma a `activities_today` |

Ninguno aporta texto a la columna.

### Marcas de tiempo y zona horaria

- **Servidor:** el día de negocio sale de `WorkSession.start_utc_offset_minutes`
  ([`dao.py:57-70`](app/routers_api/live/dao.py#L57)) — es decir, **del reloj
  del supervisor**. `session_date` se congela al crear la jornada
  ([`worksessions/models.py:69`](app/routers_api/worksessions/models.py#L69)).
- **Cliente:** las horas se formatean con
  [`formatSince`](app/components/react/entities/RouteLive/model/types/index.ts#L154):

```ts
return fecha.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
```

`toLocaleTimeString([])` usa la **zona del navegador del administrador**.

### Refresco

[`RouteTodayLivePage.tsx:27`](app/components/react/pages/RouteTodayLivePage/ui/RouteTodayLivePage.tsx#L27):
`INTERVALO_DE_REFRESCO_MS = 30_000`. La lista se reconstruye cada 30 s mientras
la selección permanece.

### ¿Jornadas duplicadas o perfiles duplicados?

**Son jornadas reales. Resuelto por restricción de base, sin consultar
producción:**

`SupervisorProfile` ([`vehicles/models.py:162-172`](app/routers_api/vehicles/models.py#L162)):

```python
Index("uq_supervisor_profile_company_user", "company_id", "user_id",
      unique=True, postgresql_where=text("deleted_at IS NULL"))
```

Y el DAO filtra `deleted_at IS NULL` + `is_active IS TRUE`
([`live/dao.py:122-124`](app/routers_api/live/dao.py#L122)). **No pueden existir
dos perfiles vivos de la misma persona en la misma compañía.**

`WorkSession` ([`worksessions/models.py:129-135`](app/routers_api/worksessions/models.py#L129)):

```python
Index("uq_work_session_one_active", "company_id", "user_id",
      unique=True, postgresql_where=text("status = 'active'"))
```

Con su comentario: *«Una jornada vigente por supervisor. Parcial a propósito:
**las cerradas pueden repetirse cuantas veces haga falta**»*.

**El modelo de datos permite N jornadas por supervisor y día de forma
explícita. Today asume una.**

## A.2 · Activity del supervisor · `/route/activity`

| Pieza | Ubicación |
|---|---|
| Página (servidor) | [`routers_pages/route/router.py`](app/routers_pages/route/router.py) · `name="RouteActivityPage"` |
| Autorización | `route.worksession.execute`, vía `exige_ejecucion_de_ruta` |
| Componente | [`RouteActivityPage.tsx`](app/components/react/pages/RouteActivityPage/ui/RouteActivityPage.tsx) |
| Endpoint | **ninguno** |

El componente íntegro:

```tsx
const RouteActivityPage = () => (
    <RouteMobileShell title="Activity" active="activity">
        <div data-testid="RouteActivityPage" className="flex flex-col gap-4">
            <NotBuiltYet feature="The Activity Explorer" checkpoint="RTE08" />
        </div>
    </RouteMobileShell>
);
```

**Estado real: `scaffold` declarado.** El propio archivo explica por qué:

> *«El Activity Explorer llega en RTE08… Enseñar aquí una jerarquía vacía daría
> la impresión de un módulo terminado sin datos, que es distinto de un módulo
> que todavía no existe.»*

Es la regla del repositorio: *«Simular lo que no está construido: una pantalla
sin backend dice que no existe en lugar de enseñar una lista vacía»*
(`AGENTS.md`, «Lo que no se hace»).

**Por qué el móvil del supervisor referencia RTE08:** porque RTE08 construyó el
Explorer **de administración** únicamente. La versión del supervisor nunca entró
en ese alcance. No es una regresión ni un fallo: es alcance no ejecutado.

## A.3 · Activity del administrador · `/admin/route/activity`

| Pieza | Ubicación |
|---|---|
| Página (servidor) | [`routers_pages/admin/route/router.py:75`](app/routers_pages/admin/route/router.py#L75) |
| Capacidad de página | `route.activity.read` |
| Endpoint | [`routers_api/activityexplorer/router.py:52`](app/routers_api/activityexplorer/router.py#L52) · `GET /api/activity-explorer` |
| Capacidad de API | `route.activity.read` — **la misma** |
| DAO | [`activityexplorer/dao.py`](app/routers_api/activityexplorer/dao.py) |
| Componentes | `features/RouteActivityExplorer/` · `ExplorerFilterBar` y la jerarquía |

**Estado real: `functional`.**

### Filtros existentes

Tres, y nada más ([`router.py:54-56`](app/routers_api/activityexplorer/router.py#L54)):
`range` (`day`/`week`/`month`/`year`), `date` (ancla) y `supervisor_user_id`.

### Estados de actividad soportados

| Nivel | Tratamiento de `IN_PROGRESS` |
|---|---|
| Agregados por día | **contados aparte**, columna `abiertos` ([`dao.py:203-214`](app/routers_api/activityexplorer/dao.py#L203)) |
| Paradas del día | **incluidas**: `paradas_del_dia` ([`dao.py:292`](app/routers_api/activityexplorer/dao.py#L292)) no filtra por `status` |

**Ninguna consulta del Explorer excluye `IN_PROGRESS`.**

### Comportamiento móvil

[`RouteActivityExplorerPage.tsx:172`](app/components/react/pages/RouteActivityExplorerPage/ui/RouteActivityExplorerPage.tsx#L172):

```tsx
showFields={!esMovil}
```

y [`ExplorerFilterBar.tsx:53`](app/components/react/features/RouteActivityExplorer/ui/ExplorerFilterBar.tsx#L53): `{showFields && (…)}`.

---

# B · Expected vs Implemented

## B.1 · Today / Live

| Esperado | Implementado | Veredicto |
|---|---|---|
| Una fila por supervisor («Select a supervisor») | una fila por **supervisor × jornada** | **Divergente** |
| Al pulsar una fila, su detalle | el detalle de la **primera** fila de esa persona | **Divergente** |
| `miles today` = millas del día | millas **de una jornada** | **Divergente** |
| `Current / Last Activity` | sólo *current*, y del **viaje**, no de la actividad | **Divergente** |
| Contadores de cabecera por persona | `len(filas)` | **Divergente** |

## B.2 · Activity del supervisor

| Esperado | Implementado | Veredicto |
|---|---|---|
| Historial propio del supervisor | marcador `NotBuiltYet` / RTE08 | **Alcance no ejecutado**, declarado |
| Restricción al usuario autenticado | no aplica: no hay endpoint | — |

## B.3 · Activity del administrador

| Esperado | Implementado | Veredicto |
|---|---|---|
| Selección autorizada de supervisor | sí, validada en servidor | **Conforme** |
| Incluir registros en curso | sí, en los dos niveles | **Conforme** |
| Filtro accesible en móvil | **ausente por diseño aprobado** | **Decisión pendiente** |
| Aislamiento por tenant | sí, por subdominio | **Conforme** |

---

# C · Causas raíz

### C-1 · `CONFIRMED` — El contrato de Today no identifica la jornada

`LiveSupervisor` carece de `work_session_id` mientras el DAO emite una fila por
jornada. La pantalla **no puede** distinguir dos filas de la misma persona,
porque el servidor no le entrega con qué.

**Evidencia:** [`live/schemas.py:53-55`](app/routers_api/live/schemas.py#L53) ·
[`live/dao.py:109-119`](app/routers_api/live/dao.py#L109)

### C-2 · `CONFIRMED` — La selección resuelve por persona y toma la primera

`find((s) => s.user_id === seleccionado)`. Consecuencia determinista del C-1, no
causa independiente.

**Evidencia:** [`RouteTodayLivePage.tsx:98`](app/components/react/pages/RouteTodayLivePage/ui/RouteTodayLivePage.tsx#L98)

### C-3 · `CONFIRMED` — El modelo permite N jornadas por día; la pantalla asume una

Índice único **parcial** sobre `status = 'active'`, con comentario explícito de
que las cerradas se repiten. Today nunca se reconcilió con esa decisión.

**Evidencia:** [`worksessions/models.py:129-135`](app/routers_api/worksessions/models.py#L129)

### C-4 · `CONFIRMED` — Los contadores de cabecera cuentan filas, no personas

`supervisors_total=len(supervisores)`. Mismo origen que C-1.

**Evidencia:** [`live/router.py:57`](app/routers_api/live/router.py#L57)

### C-5 · `CONFIRMED` — *Current / Last Activity* no muestra actividades

La columna se alimenta de `Trip.current_purpose` y existe **sólo mientras el
viaje está vigente**. El «Last» del rótulo no está implementado: cerrado el
viaje, el valor es `—`, no el último.

**Evidencia:** [`live/dao.py:299-301`](app/routers_api/live/dao.py#L299)

### C-6 · `GAP` (declarado) — `/route/activity` no construido

Marcador deliberado que referencia RTE08. No es defecto: es alcance que no se
ejecutó, documentado en el propio archivo y conforme a la norma del repositorio.

**Evidencia:** [`RouteActivityPage.tsx`](app/components/react/pages/RouteActivityPage/ui/RouteActivityPage.tsx)

### C-7 · `DECISION REQUIRED` — El filtro móvil se omite por diseño aprobado

No está ausente, ni oculto por CSS, ni fuera del viewport, ni desconectado del
estado: **el layout móvil no lo renderiza**, porque el mockup V0.7 lo pide
(`.app.device-mobile .fields-inline { display: none }`).

**Evidencia:** [`RouteActivityExplorerPage.tsx:33-37`](app/components/react/pages/RouteActivityExplorerPage/ui/RouteActivityExplorerPage.tsx#L33) y `:172` · [`ExplorerFilterBar.tsx:53`](app/components/react/features/RouteActivityExplorer/ui/ExplorerFilterBar.tsx#L53)

### C-8 · `DEVIATION` / `PENDING VALIDATION` — Asimetría de zona horaria

El **día de negocio** se decide con el desplazamiento del supervisor; las
**horas** se pintan con la zona del navegador del administrador. Si ambos no
comparten zona, `Since` se muestra desplazado.

No se ha validado si ocurre en producción: la flota observada (SC, NC, GA)
comparte zona, de modo que hoy sería invisible.

**Evidencia:** [`live/dao.py:57-70`](app/routers_api/live/dao.py#L57) ·
[`RouteLive/model/types/index.ts:154`](app/components/react/entities/RouteLive/model/types/index.ts#L154)

### C-9 · `PARTIAL` — El refresco de 30 s puede mover la selección

La lista se reconstruye cada 30 s. Si aparece una jornada nueva, el orden puede
cambiar y `find` resolver otra fila sin que nadie toque nada. Agrava C-2; sin
C-1 no tendría efecto.

**Evidencia:** [`RouteTodayLivePage.tsx:27,78`](app/components/react/pages/RouteTodayLivePage/ui/RouteTodayLivePage.tsx#L27)

### Hipótesis descartadas

| Hipótesis del planteamiento | Veredicto |
|---|---|
| El Explorer excluye registros en curso | **Descartada.** Ninguna consulta filtra por `status` |
| Las filas duplicadas son perfiles duplicados | **Descartada** por índice único parcial |
| El filtro móvil está roto o desconectado | **Descartada.** Omitido del layout, a propósito |
| Hay escalada de privilegios o fuga entre tenants | **No encontrada.** Ver §F.4 |

---

# D · Impacto funcional

| Dato | Qué le pasa | Dónde se ve |
|---|---|---|
| Millas del día por supervisor | **incorrecto** | panel: `0.0 miles today` para quien lleva 62,5 |
| Detalle del supervisor | **no corresponde** a la fila pulsada | panel lateral y vista móvil |
| `activities today` | **incompleto**: de una jornada, no del día | panel |
| Total de supervisores | **inflado** | tarjetas de cabecera |
| Actividad en curso | **no se muestra nunca** por nombre | columna *Current / Last Activity* |
| Última actividad | **no se muestra**: `—` tras cerrar el viaje | ídem |
| Historial del supervisor | **no existe** | `/route/activity` |
| Filtro de supervisor en móvil | **no disponible** | `/admin/route/activity` en móvil |

**Lo que no está afectado:** el kilometraje oficial almacenado, la evidencia de
ubicación, el Explorer de administración en escritorio y el aislamiento por
tenant. Ningún dato se está corrompiendo; se está **presentando mal**.

---

# E · Impacto en arquitectura y alcance

**Hay dos modelos de lectura distintos y deben seguir siéndolo.** `live` responde
«qué está pasando ahora» y `activityexplorer` «qué pasó». Unificarlos sería
acoplamiento innecesario y no resolvería ninguna de las causas.

**Lo que sí se puede reutilizar sin acoplar:**

| Pieza | Reutilización |
|---|---|
| `ExplorerFilterBar` | ya existe y es completo; sólo decide si se muestra |
| `dao.supervisores(company_id)` | ya es el conjunto autorizado; sirve a cualquier selector |
| Agregación por supervisor | se resuelve **dentro** de `live/dao.py`; no cruza módulos |

**Lo que no debe compartirse:** el Explorer del supervisor (C-6), si se aprueba,
necesitará su propio endpoint con el usuario autenticado como filtro fijo.
Reutilizar `/api/activity-explorer` obligaría a aceptar `supervisor_user_id` del
cliente para después ignorarlo, que es exactamente la clase de contrato ambiguo
que el invariante 2 del repositorio prohíbe.

---

# F · Propuesta de corrección mínima

Agrupada por dependencia. **Nada de esto se ha implementado.**

## F.1 · Bloque 1 — Identidad de la jornada en Today *(resuelve C-1, C-2, C-3, C-4)*

| | |
|---|---|
| **Componentes** | `live/dao.py`, `live/schemas.py`, `live/router.py`, `RouteTodayLivePage.tsx` |
| **Reutiliza** | toda la tabla y el panel actuales; no se crean componentes |
| **Impacto de API** | **aditivo**: el contrato gana campos; ninguno se retira |
| **Seguridad** | ninguno: mismos datos, misma capacidad, mismo tenant |
| **Riesgo de regresión** | **medio**: el DAO es compartido por la tabla, el panel, la vista móvil y las tarjetas |
| **Esfuerzo** | ≈ 4,1 h-agente |

Dos formas, y **la elección es del Product Owner** (ver G-1):

- **Opción A — una fila por supervisor.** El DAO agrega las jornadas del día:
  millas sumadas, actividades sumadas, estado el de la jornada vigente o la
  última. La lista vuelve a ser de personas, como dice su título. Corrige el
  `0.0` engañoso y los contadores sin tocar el frontend de selección.
- **Opción B — una fila por jornada.** Se añade `work_session_id` al contrato y
  la selección pasa a resolver por él. Más fiel a los hechos; obliga a etiquetar
  cada fila con su horario y deja a la persona dos veces en la lista.

Recomendación técnica: **A**, con las jornadas detalladas dentro del panel
cuando haya más de una. Es lo que la pantalla promete y lo que elimina el dato
incorrecto a la vista.

## F.2 · Bloque 2 — *Current / Last Activity* honesto *(resuelve C-5)*

| | |
|---|---|
| **Componentes** | `live/dao.py`, `live/schemas.py`, `LiveSupervisorTable`, `LiveSupervisorDetail` |
| **Reutiliza** | la columna existente; no se añade ninguna |
| **Impacto de API** | aditivo: un indicador de si el valor es actual o pasado, y su marca de tiempo |
| **Seguridad** | ninguno |
| **Riesgo de regresión** | **bajo**: afecta a dos celdas |
| **Esfuerzo** | ≈ 1,9 h-agente |

Cuando no hay viaje vigente, mostrar el **último viaje cerrado** con su hora, y
distinguirlo visualmente de lo que está ocurriendo (`Last: office · Greenwood ·
12:40 PM`). Decisión asociada en G-2.

**Depende del Bloque 1** cuando se elija la opción A: «el último» exige saber
primero de qué conjunto de jornadas se habla.

## F.3 · Bloque 3 — Filtro de supervisor en móvil *(resuelve C-7)*

| | |
|---|---|
| **Componentes** | `RouteActivityExplorerPage.tsx`, una línea |
| **Reutiliza** | `ExplorerFilterBar` **sin modificarlo** |
| **Impacto de API** | **ninguno** |
| **Seguridad** | **ninguno**, y es verificable: el servidor valida `supervisor_user_id` contra el conjunto autorizado y devuelve 404 si no pertenece ([`router.py:66-76`](app/routers_api/activityexplorer/router.py#L66)). Mostrar el selector **no amplía** nada |
| **Riesgo de regresión** | **muy bajo**; sólo requiere comprobar que la barra apilada cabe |
| **Esfuerzo** | ≈ 1,2 h-agente, casi todo validación responsive |

**Independiente de los demás bloques.** Puede ir primero.

## F.4 · Seguridad y alcance — sin hallazgos

Trazado completo:

| Pregunta | Respuesta | Evidencia |
|---|---|---|
| Resolución del usuario | `AuthMiddleware` → `request.state.user` / `.permissions` | `main.py:205` |
| Aislamiento de tenant | `CompanyResolverMiddleware` (subdominio) + `get_company_required` | `main.py:86` · invariante 2 |
| Alcance del admin | **toda la compañía**; no hay jerarquía | [`activityexplorer/dao.py:118`](app/routers_api/activityexplorer/dao.py#L118) |
| Supervisor restringido a sí mismo | **no aplica**: no hay endpoint de supervisor | C-6 |
| Selección autorizada en admin | sí, validada en servidor con 404 | [`router.py:70-76`](app/routers_api/activityexplorer/router.py#L70) |
| ¿Filtrado en cliente sustituye autorización? | **no**: *«la lista no se filtra en el navegador»* | [`dao.py:120-123`](app/routers_api/activityexplorer/dao.py#L120) |
| ¿Puede el estado del cliente retener contexto ajeno? | **no de forma insegura**: puede señalar la fila equivocada *del mismo tenant* (C-2); cualquier `supervisor_user_id` ajeno recibe 404 | — |

**No se ha encontrado escalada de privilegios, fuga de datos ni desajuste de
alcance.** Ninguna corrección propuesta amplía permisos.

Una observación para el registro, fuera de este diagnóstico: `/route/*` usa
`exige_ejecucion_de_ruta` en lugar de `require_page_permissions`, **más
estricta** a propósito —un superusuario de plataforma no entra al shell
operativo—, y está razonada en el archivo.

---

# G · Decisiones requeridas

Sólo lo que no se deduce de los requisitos aprobados.

### G-1 · ¿Una fila por supervisor o una por jornada?

Hoy se mezclan: el servidor emite por jornada y la pantalla identifica por
persona. Hay que elegir, y determina el Bloque 1.
*Recomendación técnica: una fila por supervisor.*

### G-2 · ¿Qué significa «Last Activity»?

La columna muestra hoy **propósitos de viaje** (`recruiting`, `client_visit`).
Mostrar la actividad real exige el detalle de `ActivityExecution`, que es otra
tabla y otro contrato.
*Recomendación técnica: mantener el propósito del último viaje cerrado, marcado
como pasado. Cambiar la semántica de la columna es un cambio de producto.*

### G-3 · ¿Se revisa la regla móvil del mockup V0.7?

Ocultar supervisor y fecha en móvil es **diseño aprobado**, no un defecto.
Mostrarlos contradice la línea base aprobada y requiere decisión expresa.

### G-4 · ¿Entra `/route/activity` (RTE08 del supervisor) en alcance?

No existe y está declarado. Es un checkpoint, no una corrección, y **no se
estima aquí** por instrucción expresa.

### G-5 · ¿Se corrige la asimetría de zona horaria (C-8)?

Requiere confirmar antes si administradores y supervisores comparten zona. Si la
respuesta es «hoy sí, mañana puede que no», conviene decidirlo ahora y no cuando
aparezca una flota en otro huso.

---

# H · Checkpoints propuestos

Unidades verificables de forma independiente, en orden de dependencia.

| # | Unidad | Depende de | Decisión | Esfuerzo | Verificable por |
|---|---|---|---|---|---|
| **H-1** | Filtro de supervisor en móvil del Explorer | — | G-3 | ≈ 1,2 h | E2E móvil: el selector existe, filtra y un id ajeno da 404 |
| **H-2** | Identidad de jornada en Today | — | G-1 | ≈ 4,1 h | integración: dos jornadas el mismo día → detalle, millas y contadores correctos |
| **H-3** | *Current / Last Activity* | H-2 | G-2 | ≈ 1,9 h | integración: con viaje vigente muestra actual; cerrado, el último con su hora |
| **H-4** | Zona horaria coherente | — | G-5 | ≈ 1,4 h | integración con dos husos distintos |
| **H-5** | Explorer del supervisor | — | G-4 | **no estimado** | fuera de este diagnóstico |

**H-1 puede entregarse de inmediato**: no toca contratos, no toca autorización y
no depende de ninguna decisión más que la suya.

**H-2 es el que corrige datos incorrectos a la vista** y debería priorizarse
sobre H-3, que es presentación.

Esfuerzo de H-1 a H-4: **≈ 8,6 h-agente**, con margen +10 % determinista y
+50 % navegador ya aplicado. Incluye pruebas y regresión, no incluye validación
de campo.

---

# Limitaciones de este diagnóstico

Dicho por delante, porque la ausencia de evidencia no es evidencia:

1. **No se ha consultado la base de producción.** La conclusión de que las dos
   filas de Karina Aguirre son dos `WorkSession` reales se deriva de las
   restricciones de esquema, que son concluyentes sobre lo que *puede* existir.
   Una consulta de solo lectura lo confirmaría en treinta segundos, y la dejo
   propuesta, no ejecutada.
2. **C-8 queda `PENDING VALIDATION`.** Depende de dónde estén administradores y
   supervisores, que es un hecho de operación y no de código.
3. **No se ha ejecutado ninguna prueba.** Este documento no afirma ningún
   resultado de suite: es lectura de código, y lo que no se ejecutó no se
   presenta como verificado.
4. **No se ha evaluado el rendimiento** de la agregación propuesta en F.1 con
   volúmenes reales. A la escala actual no es un riesgo; a mil supervisores
   habría que medirlo.

---

**Preparado para que el Product Owner apruebe instrucciones de implementación
precisas.** Ninguna línea de código, migración ni funcionalidad se ha
modificado durante esta investigación.
