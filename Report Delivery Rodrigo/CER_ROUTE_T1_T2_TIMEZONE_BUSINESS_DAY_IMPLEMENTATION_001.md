# CER Route · T-1/T-2 · Zona horaria y día de negocio — implementación

**Documento 001** · 9 de octubre de 2026
**Instrucciones:** `CER_ROUTE_T1_T2_TIMEZONE_BUSINESS_DAY_INSTRUCTIONS.md`
**Autorización:** `CER_ROUTE_T1_T2_PO_DECISION_AUTHORIZATION_001.md` — D1–D6
aprobadas con la regla de precedencia.
**Rama:** `feature/t1-t2-timezone-business-day`

---

## Status

`PENDING VALIDATION`

Implementado completo y validado con pruebas automáticas y de navegador. Queda
la **validación de campo de CER** con dispositivos y administradores reales en
zonas distintas, que ninguna prueba sustituye. Nada se declara completado por
compilar.

---

## 0 · Sobre la rama y el MR

La autorización pide seguir en la rama y el MR `!79`. **No era posible:** `!79`
(la puerta de decisión) ya estaba fusionado en `dev` y su rama borrada del
remoto. Se recreó la rama con el mismo nombre desde `dev` y la entrega va en un
**MR nuevo** (§10).

---

## 1 · AS-BUILT inicial (resumen)

Detalle completo en la puerta de decisión 001. Lo que regía antes:

| Pieza | Regla anterior |
|---|---|
| Fuente de zona | **ninguna**: sólo `utc_offset_minutes` (`-getTimezoneOffset()`) |
| `session_date` | instante + desfase del inicio; UTC sin desfase |
| «Hoy» de Today y ancla de User Activity | `business_day(company)`: desfase de **la última jornada de cualquier supervisor**; UTC sin ninguna |
| Today | **un solo día para toda la compañía**: una jornada nocturna desaparecía a medianoche |
| Horas en pantalla | **zona del navegador del administrador** |

---

## 2 · La fuente de zona elegida, y su aprobación

**Opción A adaptada**, aprobada por el PO (D1–D6):

| Columna | Qué guarda | Quién la escribe |
|---|---|---|
| `supervisor_profile.operational_time_zone` | override **opcional**, para excepciones | un administrador, en el panel existente |
| `work_session.start_time_zone` | la zona **efectiva** que se aplicó al iniciar | el servidor |

**Una sola zona efectiva por jornada** (regla de precedencia):

1. override del perfil, si es IANA válida;
2. si no, la zona IANA del dispositivo, capturada **al encolar** `Start Work`;
3. la que se aplicó se guarda en `start_time_zone` y fecha `session_date` **y**
   formatea sus horas. Nunca se guarda la del dispositivo habiendo override.

**El «hoy» de un supervisor:** su override → la zona efectiva de **su propia**
última jornada que la registró → **indeterminado**. Nunca la de otro, nunca un
desfase extrapolado, nunca UTC presentado como hora local.

`start_utc_offset_minutes` se conserva como evidencia y es lo que se muestra de
las jornadas históricas, rotulado como desfase.

---

## 3 · Expected → Implemented → Evidence → Gap

| AC | Esperado | Implementado | Evidencia | Gap |
|---|---|---|---|---|
| **AC01** | el día no depende de otra persona ni del servidor | día por supervisor; `business_day()` eliminado | `test_este_y_centro_ven_cada_uno_su_dia…`, `test_el_resultado_no_depende_de_la_zona_de_sesion_de_postgres` | — |
| **AC02** | dos zonas, dos fechas, sin interferencia | Este 04:30 UTC = día D; Centro = D−1; que el Centro empiece no mueve al Este | mismo test | — |
| **AC03** | jornada nocturna conserva `session_date`, no se cierra | visible en Today después de medianoche; métricas en su día | `test_la_jornada_nocturna_sigue_visible…` | — |
| **AC04** | instantes intactos | ningún tipo cambiado; sólo se interpreta y formatea | migración aditiva; `test_un_start_work_encolado…` (`started_at` = capturado) | — |
| **AC05** | horas en la zona del supervisor, no del navegador | `formatEventClock` compartido, en Today y User Activity | E2E: **mismo evento, navegador en Este y en Centro, misma hora**, escritorio y móvil | validación con dispositivos reales: **CER** |
| **AC06** | filtros de User Activity por `session_date`, totales intactos | sin cambios de agrupación; sólo el ancla por defecto es del supervisor | `test_activity_explorer` (26) sin cambios; `test_user_activity_abre_en_el_dia…` | — |
| **AC07** | H-2 y R-1 intactos | consolidación por persona conservada | `test_live_today` 23/23; E2E R-1 2/2 | ver §5.4 |
| **AC08** | DST determinista con IANA; históricos sin zona inventada | `zoneinfo`; histórico = desfase rotulado | `test_el_cambio_de_horario…[otono-2026, primavera-2027]`, `test_las_paradas_llevan…` | — |
| **AC09** | offline conserva instante y jornada | zona capturada al encolar; cola intacta | `test_un_start_work_encolado…`, `test_un_override_fijado_mientras_estaba_encolado…` | — |
| **AC10** | roles, tenant, navegación e interfaces | ningún permiso nuevo; ni pantallas ni menús | override: 403 supervisor, 404 otro tenant, 409 versión; catálogo y superficie pública verdes | — |
| **AC11** | esquema con aprobación y migración compatible | 2 columnas `NULL`, sin relleno, reversible | autorización del PO; `upgrade → downgrade → upgrade` sin error; un solo head | — |
| **AC12** | pruebas y E2E con evidencia | 18 de integración, 3 E2E, regresión | §6: 1098 PASS sin navegador; navegador sin fallos nuevos | segunda pasada de navegador `NOT RUN` (§6.5) |

---

## 4 · Archivos, contratos y modelo

### 4.1 · Backend

| Archivo | Cambio |
|---|---|
| `migrations/versions/0015_time_zone_sources.py` | las dos columnas; sin tocar filas |
| `worksessions/time_zones.py` (nuevo) | **la regla, en un solo sitio**: validación IANA, zona efectiva, día local, zona de referencia por supervisor |
| `worksessions/service.py`, `schemas.py`, `router.py`, `models.py` | `Start Work` aplica la precedencia antes de fijar `session_date`; audita la zona |
| `live/dao.py`, `router.py`, `schemas.py` | día por supervisor; jornada activa visible aunque sea de otro día; zona por fila |
| `activityexplorer/dao.py`, `router.py`, `schemas.py` | ancla por defecto = día del supervisor mirado; zona por parada |
| `vehicles/models.py`, `schemas.py`, `dao.py`, `service.py`, `router.py` | override: `PUT /api/supervisors/{id}/time-zone`, validado, auditado, con versión |
| `pyproject.toml`, `uv.lock` | **`tzdata` como dependencia explícita** (§7.1) |

### 4.2 · Contratos — todos aditivos

| Endpoint | Añadido |
|---|---|
| `POST /api/worksessions` | `time_zone` (opcional) |
| `WorkSessionRead` | `start_time_zone` |
| `GET /api/live/today`, cada fila | `session_date`, `time_zone`, `utc_offset_minutes`, `time_zone_determined` |
| `GET /api/live/today`, raíz | `session_date` **se conserva con su tipo**; ya no es el día de la compañía (ver docstring) y ninguna pantalla lo muestra |
| `GET /api/activity-explorer`, cada parada | `time_zone`, `utc_offset_minutes` |
| `GET /api/supervisors/candidates`, perfil | `supervisor_time_zone` / `operational_time_zone` |
| `PUT /api/supervisors/{id}/time-zone` | **nuevo**, permiso `route.vehicles.manage` |

Ningún campo existente cambia de nombre ni de tipo. **Lección de R-1 aplicada:**
un navegador con el bundle anterior ignora los campos nuevos sin romperse —Zod
descarta lo que no conoce— y sigue mostrando la hora como antes.

### 4.3 · Frontend

| Archivo | Cambio |
|---|---|
| `shared/lib/utils/utils.ts` | `deviceTimeZone()`, `eventClockParts()` y `formatEventClock()`: **una sola** regla de formato para las dos pantallas |
| `entities/RouteWorkSessions/…/workSessionService.ts` | `Start Work` envía la zona, capturada al encolar |
| `entities/RouteLive/…` y las 4 vistas de Today | `formatSince` / `sinceParts` en la zona de la jornada |
| `entities/RouteActivityExplorer/…`, `ExplorerActivityCards.tsx` | `formatClock` en la zona de la jornada |
| `entities/RouteSupervisors/…`, `SupervisorSetupPanel.tsx` | el campo opcional del override |

**Cómo se muestra la hora:**

| Caso | Ejemplo | Por qué |
|---|---|---|
| jornada con zona, navegador en la misma | `2:41 PM` | sin ruido en el caso normal |
| jornada con zona, navegador en otra | `2:41 PM EDT` | la abreviatura sale de la zona IANA |
| jornada histórica, sólo desfase | `2:41 PM UTC-04:00` | **siempre** rotulado; nunca `EDT` (D5) |
| sin zona ni desfase | `6:41 PM UTC` | no se presenta como local |
| estado que empezó otro día | `Oct 8, 11:30 PM` | una jornada nocturna no se lee como de hoy |
| zona de la persona indeterminada | `— · time zone not determined` | D3, discreto |

Comprobado con Node bajo tres zonas de navegador (Nueva York, Chicago, Madrid):
la misma hora en las tres.

**El panel:** bajo el distintivo *Yes* de cada supervisor activo, un selector
compacto con **Time zone: automatic** por defecto y las zonas de EE. UU. Sin
columnas ni pantallas nuevas.

---

## 5 · Decisiones de implementación que conviene conocer

### 5.1 · Start Work encolado y override cambiado entretanto

La jornada **nace al sincronizar**: se resuelve con el override vigente en ese
momento, la zona del dispositivo **del encolado** y el instante de ocurrencia.
Desde ese momento su zona es inmutable. Es determinista y no reinterpreta nada
después. Probado.

### 5.2 · Supervisor sin zona determinable (D3)

- **Trabajando:** se muestra su estado; sus métricas son las de la fecha de su
  jornada en curso, que es un hecho registrado, y la fila lleva la marca.
- **Sin jornada activa:** `Not started · time zone not determined`. No se afirma
  ningún día.
- **User Activity sin fecha en la petición:** abre en la fecha de su jornada más
  reciente. Es un hecho, no un «hoy» inventado. Sin ninguna jornada, la fecha
  UTC sólo ancla una vista vacía.

### 5.3 · Jornada nocturna (D4)

Visible con su estado vivo; la hora `Since` lleva la fecha (`Oct 8, 11:30 PM`).
Sus millas y actividades **no** suman en el día siguiente: Today puede mostrar
`0.0 mi` para alguien en ruta si toda su conducción es de la jornada de ayer.
Es la regla aprobada, y conviene que CER lo sepa al leer la pantalla.

### 5.4 · Las pruebas de H-2 se adaptaron, no sus aserciones

Seis pruebas de `test_live_today.py` fallaron con el cambio: iniciaban jornada
**sin zona**, como un cliente anterior, y con D3 su día es indeterminado. Se
adaptó **sólo el cuerpo** de su `Start Work` —ahora envía
`America/New_York`, como el cliente real— y **ninguna aserción**. El
comportamiento sin zona quedó cubierto aparte, con su propia prueba.

---

## 6 · Validación

### 6.1 · Integración nueva · `test_time_zones.py` · 18/18 PASS

| Bloque | Pruebas |
|---|---|
| Start Work | la zona del dispositivo fecha y se guarda · override prevalece · cambiar el override no reescribe · zona inválida no bloquea · sin zona, como antes |
| Override | validado (422), auditado (anterior/nuevo, actor, instante), se puede quitar · 403 supervisor · 404 otro tenant · 409 versión |
| Today | Este y Centro, cada uno su día y sin dependencia · nocturna visible sin mudar métricas · zona indeterminada sin inventar día · contrato aditivo |
| DST | otoño 2026 y primavera 2027, **con el desfase viejo enviado a propósito**: la fecha sale de la zona |
| Offline | encolado a las 23:50, sincronizado después · override fijado mientras esperaba |
| User Activity | paradas con su zona o su desfase · abre en el día del supervisor mirado |
| PostgreSQL | mismo resultado con la base en `Pacific/Kiritimati` (UTC+14) |

**Contra el código anterior fallan las 18.** Algunas por un motivo trivial —el
campo `time_zone` no existía y el servidor respondía 422— y se dice para no
presentarlas todas como reproducciones del defecto.

### 6.2 · Navegador · T-1/T-2 · 3/3 PASS

- **Today**, escritorio con el navegador en el **Este** y en el **Centro**, y
  móvil en el Centro: **la misma hora** en las tres; la abreviatura sólo en el
  Centro; y mostrarla **no ensancha** la tabla.
- **User Activity**, Este y Centro: la misma hora en la tarjeta.
- **Panel**: *Time zone: automatic* por defecto; elegir `America/Chicago` lo
  guarda y el API lo devuelve.

Capturas en `var/screenshots/t1-t2/`: `today-escritorio-este`,
`today-escritorio-centro`, `today-movil-centro`, `user-activity-new_york`,
`user-activity-chicago`, `panel-automatica`, `panel-override`.

**Un defecto propio, encontrado por la captura y corregido:** la primera versión
ponía la zona en la misma línea que la hora, y en la tabla de escritorio `EDT`
quedaba **cortado** contra el borde. La prueba comprobaba el texto, no si se
veía, y pasó. Ahora la hora va en su línea y la zona debajo, y la prueba
compara el ancho de la tabla con y sin zona.

### 6.3 · La E2E de R-1 que fallaba de 18:00 a 24:00

Se corrigió su fixture para no depender de `CURRENT_DATE` (lo autoriza la
instrucción; sin tocar aserciones). Al verificarlo con la base en UTC+14 —donde
`CURRENT_DATE` ya es mañana— **también pasaba la versión vieja del fixture**. La
conclusión, `CONFIRMED`: la causa no era el fixture sino el **«hoy» en UTC del
producto** (defecto D2), que T-1 corrige. El fixture queda independiente de la
zona de PostgreSQL igualmente; esa prueba no distingue los dos arreglos, y se
dice.

### 6.4 · Comprobaciones

```
uv run python -c "import app.main"          OK
alembic heads                                 0015_time_zone_sources (un solo head)
alembic upgrade → downgrade -1 → upgrade      sin errores
black (archivos tocados)                      limpio
npm run typecheck                             0 errores
npm run lint:ts                               0 errores
npm run build:prod                            compilado (2 avisos de tamaño, preexistentes)
test_permission_catalog + public_surface      21/21 PASS
```

### 6.5 · Regresión completa

| Lote | Tests | PASS | Fallos | Exit | Duración |
|---|---|---|---|---|---|
| Suite completa, 1.ª ejecución | 1281 | 1208 | **58 + 1 error** | 1 | 57 min 02 s |
| Sin navegador, tras el arreglo (§6.6) | 1114 | **1098** | 1 preexistente | 1 | 11 min 32 s |
| Navegador (de la 1.ª ejecución) | 167 | 162 | 5 preexistentes | — | — |

**Estado final:**

- **Sin navegador:** 1098 PASS = 1080 de la última regresión de `dev` + las 18
  nuevas. Único fallo: `test_provisioning_alignment` (14 frente a 12
  capacidades), que espera decisión de CER.
- **Navegador:** los 5 fallos son exactamente los que ya fallaban en `dev`
  (4 de precisión de recuperación de ubicación y 1 de durabilidad offline).
  **Ninguno nuevo**: T-1/T-2, *Keep working*, H-2 y R-1 en verde.
- La batería de navegador **no se repitió** tras el arreglo de §6.6: el
  arreglo es de una prueba de migraciones, sin navegador, y la cascada sólo
  afectó a pruebas de integración. `NOT RUN` como segunda pasada.

### 6.6 · Lo que falló en la 1.ª ejecución, y por qué · `CONFIRMED`

**51 fallos y 1 error en cascada, en 9 archivos de integración**
(`location_evidence`, `mileage_engine`, `missing_immutability`,
`exact_correlation`, `foundation`, `admin_configuration`, `access_model`,
`notes_migration_safety` y la propia `recovery_accuracy_migration`).

La causa era **una prueba con un defecto latente**:
`test_recovery_accuracy_migration` tenía el head escrito como constante
—`"0014_recovery_accuracy"`— desde cuando la 0014 era el último. Con la 0015
nueva, su round-trip devolvía la base **sólo hasta la 0014**: sin las columnas
de zona. Desde ese momento, en ese worker, todo `Start Work` respondía *«A
database error prevented completing the request»* y las pruebas siguientes
caían en cadena.

**Corrección:** la prueba lee el head real de Alembic. Lo que comprueba de la
0014 —el motivo nuevo, su round-trip, la bajada que se niega— no cambia.
Verificado: los 9 archivos en un solo proceso, **205 PASS**, y la regresión
sin navegador limpia.

Que la bajada fallida no deje la base a medias está garantizado por la
configuración: Alembic corre toda la ejecución en **una** transacción y
PostgreSQL deshace también el DDL.

### 6.7 · Hallazgo incidental · dependencia de orden entre dos pruebas · `CONFIRMED`

`test_recovery_accuracy_migration` deja un hecho con el motivo nuevo en
`missing_location_event`, que es append-only. Si
`test_route_notes_migration_safety` se ejecuta **inmediatamente después en el
mismo proceso**, la migración 0014 se niega —correctamente— a bajar, y la
prueba da error. En una ejecución normal no ocurre, porque cualquier prueba con
`seeded` intermedia vacía las tablas; reproducido a propósito, ocurre.

**No lo causa T-1/T-2** y no se corrige aquí: ninguno de los dos archivos se
tocó salvo la constante del head. Arreglarlo es que la primera prueba limpie su
propia fila con el mismo patrón que ya usa `seeded`.

---

## 7 · Limitaciones y acciones operativas

### 7.1 · `tzdata`, dependencia nueva explícita

`zoneinfo` necesita la base de zonas. En Windows llegaba como dependencia
indirecta; en el Linux de producción dependería de que la imagen la traiga, y
**no está verificado**. Se declaró `tzdata` en `pyproject.toml`. El despliegue
la instala con el resto.

### 7.2 · La transición, el día del despliegue · **acción operativa**

Hasta que cada supervisor haga su primer `Start Work` con el bundle nuevo, **no
tiene zona registrada**: sus jornadas anteriores sólo tienen desfase, y D3
prohíbe extrapolarlo. Ese día, quien ya hubiera cerrado su jornada saldrá
`Not started · time zone not determined`. Quien esté trabajando se ve con
normalidad.

- **Pedir a los supervisores que recarguen la aplicación** antes de su siguiente
  `Start Work`: un teléfono con el bundle anterior en caché no envía la zona y
  seguirá indeterminado. Es la misma acción que R-1.
- Si algún supervisor necesita su zona desde el primer momento, **fijar el
  override** en el panel.

### 7.3 · Lo que no cambia

- **My Route y My Activity** del supervisor formatean en su propio navegador,
  que **es** su zona: correcto, sin cambio.
- **El panel de excepciones de odómetro** muestra la hora de la solicitud en la
  zona del administrador. No es un horario de jornada; queda fuera de T-1/T-2 y
  se anota.
- La raíz `session_date` de Today queda **obsoleta** (§4.2).

### 7.4 · Hallazgo incidental · la tabla de Today desborda 16 px a 1280

Con un nombre en dos líneas y cinco columnas, la tabla de escritorio ocupa 651
px en un contenedor de 635. **No lo causa T-1/T-2**: ocurre igual con el
navegador en el Este, donde la celda muestra exactamente lo mismo que antes
(`LIKELY` preexistente; no medido con el bundle anterior). No se toca: sería
rediseñar la tabla.

---

## 8 · Estimación

| Tarea | Volumen | Complejidad | Horas-agente |
|---|---|---|---|
| AS-BUILT de implementación | — | — | 1,0 |
| Migración, helper de zonas, Start Work | ~270 LoC | dominio | 1,8 |
| Today por supervisor y User Activity | ~280 LoC | dominio | 2,0 |
| Override: servicio, endpoint, auditoría | ~140 LoC | determinista | 1,0 |
| Frontend: formato, captura, Today, User Activity, panel | ~270 LoC | UI | 4,5 |
| Integración (18), adaptación de H-2 y arreglo de la prueba de migraciones | ~640 LoC | integración | 7,0 |
| E2E (3) con dos zonas de navegador, y R-1 | ~260 LoC | navegador | 4,5 |
| Verificación contra el código anterior, migración, DST en Node | — | — | 1,5 |
| Regresión (dos pasadas), diagnóstico de la cascada, reporte y entrega | — | — | 3,5 |
| **Total** | **≈ 1800 líneas** | | **≈ 26,5 h** |

Estimado en la puerta de decisión: ≈ 28 h con margen. Dentro.

---

## 9 · Fuera de alcance, sin tocar

P-2 (jornadas olvidadas), H-3, H-1. Kilometraje, odómetro, viajes, actividades,
cola offline y motor de permisos. `test_provisioning_alignment` sigue fallando
igual: espera decisión de CER.

---

## 10 · Git

`PENDIENTE`
