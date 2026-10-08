# CER Route · Ending Odometer — «I can't take a photo» ya no cierra el día

**Reporte 001** · 7 de octubre de 2026
**Alcance:** la brecha reportada en `End Work → Ending Odometer`, y nada más.
**Rama:** `fix/ending-odometer-manual-entry`

---

## Status

`COMPLETED WITH PENDING VALIDATION`

La corrección está implementada y validada en integración y en navegador,
incluida la comprobación de que los tests nuevos **fallan con el código
anterior**. Queda pendiente la validación de campo de CER y una decisión humana
sobre un hallazgo incidental ajeno a este cambio (ver §7).

---

## 1 · Causa raíz · `CONFIRMED`

El comportamiento reportado no era un descuido de implementación: era una
**decisión de negocio anterior de CER** —la «Opción B» de C4— escrita a
propósito en dos sitios que se refuerzan.

### 1.1 · El frontend cerraba la jornada al enviar la solicitud

`app/components/react/pages/RouteMyRoutePage/ui/RouteMyRoutePage.tsx`

En la fase `ending`, el callback `onChanged` del componente de odómetro estaba
cableado directamente a `cerrarJornada`:

```tsx
onChanged={async () => {
    // Pedida la excepción, el día ya puede cerrarse: la evidencia queda
    // pendiente y `ended_at` se escribe a su hora real.
    await cerrarJornada(view.session, true);
}}
```

Y `OdometerCapture.pedirExcepcion` dispara `onChanged()` justo después de
enviar la solicitud. Por tanto: `Send request` → `onChanged` → cierre
inmediato. El supervisor **nunca llegaba** al campo manual.

### 1.2 · El servidor lo autorizaba

`app/routers_api/odometer/models.py`

```python
END_WORK_UNBLOCKING_STATUSES = RESOLVED_STATUSES + (
    OdometerStatus.EXCEPTION_REQUESTED.value,
    OdometerStatus.EXCEPTION_APPROVED.value,
)
```

`ensure_end_work_not_blocked` aceptaba esos dos estados, así que aunque el
frontend no hubiera cerrado el día, una petición directa a `End Work` también
habría pasado sin lectura.

### 1.3 · Por qué existía, y qué falló en el razonamiento

La Opción B evitaba un problema real: retener la jornada abierta esperando a
que un administrador revisara la solicitud escribiría un `ended_at` que no
ocurrió, y la hora de fin de jornada es un dato laboral.

Lo que no se previó es el efecto combinado: pedir la excepción se convirtió en
**la forma de no dar la lectura**. `Ending Odometer` quedaba `Missing` de forma
permanente y la distancia del día no se podía afirmar.

La instrucción de corrección resuelve el problema original por el otro lado, y
es mejor: en el cierre la excepción se aprueba al enviarse, así que el
supervisor teclea en el acto y **nadie espera a nadie**. El motivo de la Opción
B desaparece en vez de ser ignorado.

---

## 2 · La trampa que había que resolver · `CONFIRMED`

Bloquear el cierre no era suficiente, y por sí solo habría sido **peor** que el
defecto.

`confirm_reading` exige, para teclear sin foto, una excepción **aprobada**
(`find_approved`). La capacidad que la aprueba al instante,
`route.odometer.selfapprove`, **no se concede a ningún rol por defecto** —está
declarada fuera de `DEFAULT_ROLES` a propósito—.

Con sólo el bloqueo, un supervisor sin esa capacidad quedaba **atrapado**:

* no podía teclear la lectura, porque su solicitud esperaba revisión;
* no podía cerrar el día, por el bloqueo nuevo;
* y su jornada quedaba abierta indefinidamente.

Es la misma trampa del defecto 4 de la puerta de ubicación, corregido ayer.

**Decisión aplicada:** en el extremo de **cierre**, la excepción se aprueba al
enviarse, siempre e independientemente de cualquier capacidad. El extremo de
**inicio** no se toca: ahí la aprobación protege algo concreto —que nadie salga
a conducir sin evidencia de dónde empezó— y sigue esperando al administrador.

Esta lectura es la única que hace posible lo que la instrucción pide
textualmente («presentar **inmediatamente** un campo», AC1 y AC2 sin
condiciones). El resultado es **más estricto en evidencia** que antes: donde el
día cerraba sin lectura, ahora no cierra sin ella.

---

## 3 · Componentes y API afectados

| Archivo | Cambio |
|---|---|
| `app/routers_api/odometer/models.py` | `END_WORK_UNBLOCKING_STATUSES` pasa a ser igual a `RESOLVED_STATUSES`: sin lectura confirmada, el día no cierra |
| `app/routers_api/odometer/service.py` · `request_exception` | en `end`, la solicitud nace `approved`; en `start`, sin cambios |
| `app/routers_api/odometer/service.py` · `confirm_reading` | en `end` basta una solicitud **viva** (`find_open`); en `start` sigue exigiendo `find_approved` |
| `app/routers_api/odometer/service.py` · `ensure_end_work_not_blocked` | bloquea los estados de excepción; mensaje distinto según si ya está autorizado a teclear |
| `RouteMyRoutePage.tsx` | en fase `ending`, `onChanged` **relee la evidencia** en vez de cerrar la jornada |
| `OdometerCapture.tsx` | en `end`, `exception_requested` también habilita el campo; textos que distinguen inicio de cierre |

**Ningún endpoint nuevo, ninguna migración, ningún cambio de esquema.** La
`API` pública es la misma; lo que cambia es qué estados acepta la guarda de
cierre.

### 3.1 · Dos consecuencias declaradas

1. **Las excepciones de cierre ya no llegan a la cola del administrador.**
   Nacen aprobadas, así que no hay nada que decidir —`decide_exception` exige
   `requested`— y no aparecen en `/odometer/exceptions/pending`. Las de inicio
   siguen pasando por la cola igual que antes. Hay un test que fija esta
   asimetría para que un cambio futuro que la rompa haga fallar algo.
2. **La trazabilidad se conserva y se mejora.** La aprobación automática emite
   un evento `auto_approve` propio, nunca `approve`, y su resumen **nombra el
   motivo**: `because the ending reading is required to end the day` frente a
   `under route.odometer.selfapprove`. Quien lea la auditoría puede distinguir
   una decisión humana de una regla, y cuál de las dos reglas fue.

---

## 4 · Pruebas ejecutadas

### 4.1 · Integración · 65/65 PASS

```
tests/integration/test_odometer_end_work.py              15 PASS
tests/integration/test_odometer.py
tests/integration/test_odometer_exception_autoapproval.py
tests/integration/test_odometer_photo_retention.py       50 PASS
                                                      -------
                                                         65 PASS  exit 0
```

Los tests mínimos que pedía la instrucción, y dónde están:

| Caso pedido | Test |
|---|---|
| Photo → lectura → Confirm → End Work | `test_the_normal_end_photo_path_closes_the_day_and_the_distance` |
| Can't take photo → Request → manual → Confirm → End Work | `test_the_manual_end_reading_then_closes_the_day` |
| Can't take photo → Request → sin lectura → NO cerrar | `test_requesting_the_end_exception_does_not_end_the_day` y `test_the_day_stays_open_until_the_reading_is_confirmed` |
| Manual ending < starting → rechazado | `test_a_manual_end_reading_below_the_start_is_rejected` |
| Refresh/back durante el ingreso manual | en el E2E, §4.2 |

Tests añadidos más allá del mínimo, por riesgos concretos:

* `test_an_unreviewed_request_from_before_the_fix_can_still_be_typed` — las
  jornadas que quedaron con una solicitud de cierre sin revisar bajo la regla
  anterior. **Son datos reales en producción**, no una hipótesis: con la regla
  nueva y sin esta tolerancia quedarían atrapadas.
* `test_the_start_exception_still_waits_for_an_administrator` — el control que
  no se tocó y que esta corrección podría haber roto por arrastre.
* `test_the_end_exception_no_longer_reaches_the_admin_queue` — la consecuencia
  de §3.1, comprobada en vez de supuesta.
* `test_the_manual_end_reading_is_fully_audited` — incluye que **no** se emita
  un `approve` humano, porque decirlo así sería inventar un decisor.

### 4.2 · Navegador · 1/1 PASS

`tests/e2e/test_trip_and_odometer_browser.py::test_i_cannot_take_a_photo_leads_to_the_manual_ending_reading`

Recorre el flujo como una persona: `End Work` → `I can't take a photo` →
`Send request` → aparece el campo → **se recarga la página a mitad** → el campo
sigue ahí y la jornada sigue activa → se teclea una lectura imposible y se
rechaza sin cerrar → se teclea la buena → el día cierra con distancia `96.0`.

### 4.3 · La comprobación que da valor a los tests · `CONFIRMED`

El E2E se ejecutó **contra el código anterior**, revirtiendo sólo `app/` y
reconstruyendo el bundle:

```
tests\e2e\test_trip_and_odometer_browser.py:677: AssertionError
  Locator expected to have count '1'
```

La línea 677 es la que espera el campo `#odometer-reading` después de
`Send request`. Es exactamente el defecto reportado, reproducido.

Después se restauró la corrección, se reconstruyó el bundle y el test vuelve a
pasar.

### 4.4 · Un error propio, reportado

El primer PASS del E2E **no validaba el frontend**. El bundle servido era de
las 16:49 y mis cambios de `.tsx` eran de las 19:34: `npm run check` hace
typecheck y lint, no `build`. El test pasó porque el arreglo del servidor
corrige el defecto por sí solo —el 409 devuelve al supervisor a la pantalla de
odómetro, que al ver `exception_approved` ya ofrece el campo—.

Se detectó comparando marcas de tiempo, se ejecutó `npm run build:prod` y se
repitió. El cambio de frontend sigue siendo necesario: evita un viaje
redundante al servidor y el parpadeo de cierre que el supervisor vería.

### 4.5 · Typecheck y lint

```
npm run typecheck   0 errores
npm run lint:ts     0 errores
npm run build:prod  compilado (2 warnings de tamaño de bundle, preexistentes)
```

### 4.6 · Regresión completa

`PENDING` al momento de redactar: la suite sin navegador está en ejecución. El
resultado se añade antes de abrir el MR.

---

## 5 · Acceptance Criteria

| AC | Estado | Evidencia |
|---|---|---|
| AC1 · Submit Request lleva al ingreso manual, no al cierre | `VALIDATED` | E2E §4.2 + `test_requesting_the_end_exception_does_not_end_the_day` |
| AC2 · El usuario puede ingresar y confirmar manualmente | `VALIDATED` | `test_the_manual_end_reading_then_closes_the_day` |
| AC3 · Confirmada una lectura válida, la jornada cierra | `VALIDATED` | mismo test, + distancia `88.0` |
| AC4 · Sin lectura válida, la jornada permanece abierta | `VALIDATED` | `test_the_day_stays_open_until_the_reading_is_confirmed`, incluido con `end_anyway` |
| AC5 · `Ending Odometer` no queda `Missing` por este flujo | `VALIDATED` | E2E: `manual_exception_confirmed` + `manual_no_photo` |
| AC6 · Ending < Starting es rechazado | `VALIDATED` | `test_a_manual_end_reading_below_the_start_is_rejected` (422) + E2E |
| AC7 · El flujo normal por fotografía sigue igual | `VALIDATED` | `test_the_normal_end_photo_path_...` y los 50 tests de odómetro |
| AC8 · `Keep working` y el resto de `End Work` sin cambios | `VALIDATED` | no se tocó ese código; `test_the_trip_blocker_is_resolved_before_the_end_reading` sigue verde sin modificación |

---

## 6 · Lo que cambió en los tests existentes, y por qué

La regla anterior estaba **certificada por una familia de tests**. Siete de
ellos afirmaban literalmente lo contrario de lo que ahora se pide, así que
reescribirlos no es un ajuste cosmético: es el coste real de invertir la
decisión, y conviene que quede dicho.

| Test anterior | Qué se hizo |
|---|---|
| `test_the_day_ends_with_the_end_exception_still_unreviewed` | **invertido**: ahora comprueba que la jornada **no** cierra |
| `test_completing_the_end_reading_later_never_moves_ended_at` | sustituido: ya no hay lectura «tardía»; el día cierra con la lectura dentro |
| `test_completing_the_end_reading_later_creates_no_trip` | adaptado al flujo nuevo |
| `test_a_photo_cannot_be_added_once_the_day_is_closed` | conservado; cambia el estado previo y añade que la foto tardía no reescribe `evidence_method` |
| `test_a_rejected_end_exception_leaves_the_evidence_pending` | sustituido por `test_the_end_exception_no_longer_reaches_the_admin_queue`: en el cierre ya no hay rechazo posible |
| `test_an_end_approval_is_single_use_too` | conservado sin la aprobación manual |
| `test_the_late_end_reading_is_fully_audited` | reescrito: el evento es `auto_approve`, no `approve` |
| `test_retirar_la_capacidad_restaura_el_flujo_anterior` | usaba el extremo de cierre para probar la capacidad; ahora usa el de inicio, que es donde la capacidad decide |

El docstring del archivo se reescribió para que explique **qué había antes y
por qué se cambió**. Nadie debería tener que reconstruir esta decisión desde
`git log`.

---

## 7 · Hallazgo incidental · requiere decisión de CER

`tests/integration/test_provisioning_alignment.py::test_the_two_product_roles_hold_exactly_twelve_and_two_capabilities`

**FALLA, y falla también con el código de `dev` sin esta corrección** —se
verificó revirtiendo los cambios—. No lo causa este trabajo.

```
AssertionError: 'route_admin': 14 capacidades, se esperaban 12
```

La plantilla del rol Administrador tiene hoy 14 capacidades. Las dos que
sobran respecto de lo certificado son `route.live.read` (RTE07) y
`route.activity.read` (RTE08): se añadieron en esos checkpoints y el número
certificado no se actualizó.

**El test está funcionando exactamente como se diseñó.** Su propio docstring lo
dice: *«que el Administrador tenga doce y el Supervisor dos es lo que CER
certifica. Si mañana alguien añade una capacidad a una plantilla sin pasar por
CER, esto falla y obliga a decirlo».*

Por eso **no se ha tocado**. Cambiar el 12 por un 14 sería precisamente lo que
el control existe para impedir: convertir en verde una ampliación de privilegio
que nadie aprobó.

**Acción operativa:** CER debe confirmar que el rol Administrador tiene ahora 14
capacidades, incluidas las dos de lectura operativa. Con esa confirmación, el
cambio del número es de un minuto. Es revisión humana, no un fallo de
ingeniería.

---

## 8 · Estimación del trabajo realizado

| Tarea | Volumen | Complejidad | Horas-agente |
|---|---|---|---|
| Diagnóstico de causa raíz y de la trampa de aprobación | — | análisis | 1,6 |
| Backend: guarda, aprobación del cierre, tolerancia a lo heredado | ~90 LoC | dominio | 0,6 |
| Frontend: recarga en vez de cierre, estados y textos | ~60 LoC | UI | 1,1 |
| Tests de integración (reescritura + 5 nuevos) | ~420 LoC | integración | 4,7 |
| E2E del flujo corregido, con recarga a mitad | ~130 LoC | navegador | 3,3 |
| Verificación contra el código anterior (revertir, 2 builds, 3 corridas) | — | navegador | 1,4 |
| Regresión, MR y este reporte | — | — | 1,5 |
| **Total** | **550 añadidas / 245 borradas** | | **≈ 14,2 h** |

Márgenes declarados: **+10 %** en dominio y UI (deterministas), **+50 %** en
navegador.

---

## 9 · Git

| | |
|---|---|
| Rama | `fix/ending-odometer-manual-entry` |
| Base | `dev` en `82c78c8` |
| Commit | se añade al cerrar el reporte |
| MR | se añade al cerrar el reporte |
| Fusionado | **No.** CER certifica; el desarrollo no fusiona |

---

## 10 · Trabajo restante y acción operativa

Lo que este cambio **no** hace y tiene que ocurrir en otro sitio:

1. **Validación de campo (CER).** El flujo manual completo en un teléfono real,
   con un supervisor que de verdad no puede fotografiar el cuentakilómetros.
   `IMPLEMENTED` no es `VALIDATED`.
2. **Decisión sobre las 14 capacidades** del rol Administrador (§7).
3. **Las jornadas abiertas ahora mismo** con una solicitud de cierre sin
   revisar pasan a poder cerrarse en cuanto se despliegue esto: el supervisor
   verá el campo y tecleará. No hace falta migración ni intervención, pero
   conviene saberlo antes de que ocurra.
4. **Las excepciones de cierre pendientes en la cola del administrador**
   dejarán de aparecer ahí (§3.1). Si hay alguna viva, se resuelve sola cuando
   su supervisor teclee la lectura.

## 11 · Siguiente paso

Cerrar la regresión completa, commit, push con MR y actualizar §4.6 y §9 de
este reporte. No se empieza nada más: lo pedido era esta brecha.
