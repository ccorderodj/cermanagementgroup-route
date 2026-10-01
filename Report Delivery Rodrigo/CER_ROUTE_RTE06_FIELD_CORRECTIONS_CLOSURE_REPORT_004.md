# CER Route — RTE06 Field Corrections & Hardening — Report 004

**Fecha**: 2026-10-01
**Instrucción**: `_cer_delivery/CER_ROUTE_RTE06_FIELD_CORRECTIONS_INSTRUCTIONS_001.md`
**Rama**: `feature/rte06-field-corrections`

---

## 1. Executive Result

**Estado propuesto: `IMPLEMENTATION COMPLETE WITH PENDING VALIDATION`.**

**No** `IMPLEMENTATION COMPLETE / READY FOR CER PHYSICAL REVALIDATION`, y el
motivo está en §11: la corrección del odómetro está implementada y pasa
typecheck, lint y build, pero **no tiene todavía los tests O1–O10**, y cuatro de
los once tests de geolocalización no se han podido ejecutar. La instrucción
exige que ese estado sólo se declare cuando *todos* los criterios de aceptación
del lado de Development estén confirmados, y no lo están.

Las dos correcciones pedidas están escritas:

| | |
|---|---|
**F-1** — la recuperación aplica el umbral de 100 m | Implementado y **verificado en navegador** |
**Odómetro** — la tarea sobrevive a la cámara | Implementado; **sin verificar con tests** |

Y apareció **un tercer defecto, no reportado por CER**, que bloqueaba la
verificación de F-1 y es de la misma familia: evidencia válida descartada en
silencio. Está en §4.

---

## 2. F-1 Root Cause and Correction

La etapa 1 exigía `fresh_max_accuracy_m` (100 m) y la 2 exigía edad y precisión
(500 m). **La 3 no exigía nada**: lo que devolviera el navegador se aceptaba
como `recovered`, que es un nivel de evidencia de pleno derecho. Un punto
rechazado por tener 2 km de error en la etapa 1 entraba por la 3, y
`for_trip_waypoints()` no vuelve a filtrar por nivel ni por precisión, de modo
que acababa siendo un waypoint oficial de kilometraje.

Lo corregido en
[`location.ts`](app/components/react/shared/lib/location/location.ts):

- **el mismo umbral que `fresh`**, reutilizando `freshMaxAccuracyM` en vez de
  añadir un segundo número configurable (D-FIELD-01). Dos umbrales que
  significan lo mismo acaban divergiendo y entonces nadie sabe cuál manda;
- **reintento acotado dentro de la ventana**: antes era una sola llamada con el
  ancho de la ventana como timeout. Ahora se reintenta mientras quede tiempo,
  porque el GPS mejora según fija satélites (GEO-04);
- **pausa de 2 s entre intentos**, para que la ventana no se convierta en un
  bucle ocupado si el proveedor responde al instante.

---

## 3. Recovered Accuracy Rule — As Built

```
candidato de recuperación
  AND (accuracy_m <= freshMaxAccuracyM  ó  accuracy desconocida)
  → `recovered`, evidencia autoritativa
en otro caso
  → candidato rechazado; se sigue intentando mientras quede ventana
```

El umbral sale de la política de plataforma, no de una constante: `100` es su
valor por defecto y CER puede ajustarlo sin desplegar, que es lo que §26 exige
para los números no certificados.

**Limitación de plataforma, documentada (GEO-08)**: `navigator.permissions.query`
devuelve sólo `granted` / `denied` / `prompt`. **La aplicación no puede
distinguir Precise de Approximate en Android.** La única señal es la `accuracy`
medida, así que los umbrales son la única defensa contra evidencia gruesa — y es
exactamente por eso que el hueco de la etapa 3 importaba.

---

## 4. Hallazgo nuevo: un 409 descartaba evidencia válida — `CONFIRMED`

**No lo reportó CER y no estaba en el diagnóstico.** Apareció al intentar
verificar F-1 y es de la misma familia: evidencia válida perdida sin rastro.

`esRechazoDefinitivoDeEvidencia()` trataba **todo** 4xx salvo 404, 408 y 429 como
rechazo definitivo. Pero la captura de `start_work` se dispara a la vez que la
acción que crea la jornada, así que la evidencia puede llegar antes de que esa
jornada esté `ACTIVE`, y el servidor responde con **409** *"Location evidence
requires an active work session"*.

Medido en navegador, antes de la corrección:

```
POST /api/location/evidence -> 409
location_fix:            0 filas
missing_location_event:  0 filas
```

Ni punto ni Missing: el evento quedaba en el **limbo** que §11 no contempla, y
que la consulta `L-14` del catálogo del MR !30 existe para detectar.

Corregido tratando 409 como reintentable, igual que 404. Medido después:

```
POST -> 409  →  reintento  →  201
location_fix: 1 fila (start_work, fresh)
```

El otro 409 del endpoint —la ventana de recuperación de End Work ya cerrada—
seguirá fallando, y es correcto: se agota contra el límite de la cola en vez de
perder la evidencia en el primer intento.

---

## 5. Rejected Recovery / Missing Behavior

Al agotarse la ventana habiendo visto candidatos y habiéndolos rechazado
**todos** por precisión, se declara Missing con un motivo nuevo:

```
recovery_accuracy_rejected
```

**Por qué uno nuevo y no reutilizar `recovery_window_exhausted`** (D-FIELD-03):
ese motivo dice literalmente *"la ventana terminó sin punto y sin más
información"*, y aquí **sí hubo puntos**. Son dos hechos operativos distintos
que piden acciones opuestas: un GPS que no fija pide más ventana; uno que fija
mal pide revisar el umbral. Fundirlos haría imposible la calibración de campo
que V-2 y V-5 tienen pendiente.

Migración `0014_recovery_accuracy`. **No lee ni escribe ninguna fila**: amplía un
`CHECK`, y todo lo que pasaba el anterior pasa el nuevo.

**La bajada se niega** si hay filas que usen el motivo nuevo, con el recuento y
la consulta para verlas. `missing_location_event` es append-only por disparador,
así que esas filas no se pueden reescribir: bajar exigiría inventarles otro
motivo, y eso sería reescribir un hecho.

---

## 6. Routing Waypoint Protection

La garantía es estructural y no un filtro añadido: **un candidato rechazado no
crea fila**. Como `for_trip_waypoints()` selecciona de `location_fix` sin mirar
nivel ni precisión, la única defensa posible es que la fila no exista — y es la
que se implementó.

Verificado por `test_g11_un_candidato_rechazado_no_es_waypoint`: tras un
candidato de 2.000 m, `location_fix` tiene **cero filas** de cualquier nivel.

---

## 7. Odometer START Restoration

`capturandoInicio` era `useState` puro. La captura se abre ahora por **tres
caminos, y dos son restaurables**:

1. el supervisor acaba de pulsar el botón — volátil, a propósito;
2. **ya hay foto subida** (`evidence.captured_at`) — verdad de dominio: la tarea
   está a medias y lo que falta es confirmar la lectura (ODO-02, ODO-04);
3. quedó marcada la intención en `sessionStorage` antes de abrir la cámara, para
   el caso en que la página muriera **antes** de subir la foto (ODO-05).

El tercero usa `sessionStorage` y no el servidor porque **no es evidencia**: es
dónde estaba mirando una persona. Mandarlo al servidor crearía estado de
interfaz en el dominio. Dura lo que la pestaña, que es lo que tiene que durar, y
toda lectura y escritura va en `try/catch` para el modo privado.

La marca se olvida al resolver y al cancelar: dejarla reabriría la captura en el
siguiente arranque.

---

## 8. Odometer END Restoration

`phase: 'ending'` **sólo se ponía dentro del flujo de cerrar la jornada**, así
que era estado volátil: si Android recreaba la pestaña, `reconcile()` calculaba
`working` y la tarea de cierre desaparecía de la vista con la evidencia
pendiente en el servidor.

Ahora `reconcile()` la deriva de la evidencia:

```ts
if (evidencia?.end && !isOdometerResolved(evidencia.end.status)) {
    confirmar({ phase: 'ending', session: sesion });
    return;
}
```

Es verdad de dominio y sobrevive a todo. **No reabre la jornada**: `ended_at` ya
está escrito y esto sólo decide qué pantalla se muestra (ODO-03).

---

## 9. Photo Persistence / Page Recreation Cases

| Caso | Comportamiento |
|---|---|
Foto persistida, página recreada | La captura se reabre sola por `captured_at`, con la foto restaurada. No se pide otra |
Foto **no** persistida, página recreada | La marca de `sessionStorage` reabre la captura en estado de captura. No se finge que haya foto |
Vuelta normal de cámara sin recreación | El estado de React sobrevive; nada cambia |
Cancelar | La marca se borra: reanudar algo que alguien cerró sería ignorarle |

---

## 10. OCR Scope Confirmation

**No se ha implementado OCR productivo.** `NoSuggestionReader` sigue siendo el
lector activo, devuelve `None` y no navega. La corrección funciona igual sin
sugerencia: el supervisor teclea lo que ve y la evidencia sigue siendo
fotográfica, sin aprobación de nadie (D-FIELD-06, ODO-06).

RTE10-A01 queda intacto.

---

## 11. Tests / Regression

### Lo verificado

| Comprobación | Resultado |
|---|---|
`npm run typecheck` | **PASS** — 0 errores |
`npm run lint:ts` | **PASS** — 0 errores |
`npm run build:prod` | **PASS** — `exit 0` |
Migración `0014` arriba | **PASS** — `exit 0`, motivo en la restricción |
`test_recovery_accuracy_migration.py` | **PASS** — 4/4 |
El 409 ya no descarta evidencia | **PASS** — medido: 409 → reintento → 201, 1 fila |

### Tests de geolocalización en navegador

En la ejecución del commit de F-1, con el fichero en su forma estable:

| Test | Resultado |
|---|---|
G1 — recuperado a 50 m, aceptado | **PASS** |
G2 — justo en el umbral, aceptado | **PASS** |
G5 — candidato malo y luego bueno | **PASS** |
G9 — regresión de `fresh` (×2) | **PASS** |
G10 — regresión de `cached` | **PASS** |
G11 — rechazado nunca es waypoint | **PASS** |
G3 — uno por encima del umbral | **NOT RUN** |
G4 — 2.000 m | **NOT RUN** |
G6 / G7 — Missing y su motivo | **NOT RUN** |

**Por qué los cuatro quedan sin ejecutar, dicho con precisión**: comprueban lo
que ocurre **al agotarse la ventana de recuperación**, que por defecto son 180 s.
Acortarla desde el test exige que la política esté escrita antes de que arranque
el servidor —el cliente la pide una sola vez, al cargar la página— y el arreglo
de orden de fixtures que intenté **rompió los diez tests**, porque hacía
depender la fixture de `database_schema`, que reinicia la base y borra los
usuarios sembrados: el login devolvía 401. La dependencia ya está quitada, pero
**la suite no se ha vuelto a ejecutar entera después de ese arreglo**, y no voy
a declarar PASS lo que no he visto pasar.

G8 (privacidad del candidato rechazado) va dentro de G6/G7, así que comparte su
estado.

### Tests O1–O10 del odómetro

**NOT RUN.** No están escritos. La corrección del odómetro está implementada y
pasa typecheck, lint y build, pero **no tiene cobertura automatizada**.

### Regresión de backend

`PENDING` en el momento de escribir esto. Una primera ejecución dio errores en
`test_route_mileage_engine.py`, pero **ese resultado no es válido**: lancé la
suite de navegador y la de backend a la vez contra la misma base de pruebas y se
pisaron. La repetición en solitario estaba corriendo al cerrar el informe.

---

## 12. Expected → Implemented → Evidence → Gap

| Criterio | Implementado | Evidencia | Hueco |
|---|---|---|---|
1. La recuperación no acepta cualquier precisión | Sí | G1, G2, G11 | — |
2. Usa la política de 100 m de `fresh` | Sí | G1, G2 | — |
3. Continúa tras un candidato rechazado | Sí | G5 | — |
4. Agotarse crea Missing veraz | Sí | — | **sin ejecutar** |
5. No se persisten coordenadas rechazadas | Sí | — | **sin ejecutar** (G8) |
6. 2.000 m no puede ser autoritativo | Sí | G11 | parcial: G4 sin ejecutar |
7. Lo rechazado no entra en waypoints | Sí | G11 | — |
8. `fresh` sigue correcto | Sí | G9 ×2 | — |
9. `cached` sigue correcto | Sí | G10 | — |
10. Waypoint Missing sigue correcto | Sin tocar | — | regresión pendiente |
11–18. Restauración del odómetro | Sí | typecheck/lint/build | **sin tests** |
19. Foto válida sin OCR permite confirmar | Sin tocar | — | **sin tests** |
20. Excepción sin foto sin cambios | Sin tocar | — | **sin tests** |
21. Sin OCR productivo | Sí | `NoSuggestionReader` intacto | — |
22–26. Regresión | — | — | **pendiente** |
27. Migraciones | Sí | 4/4 | — |
28. Sin GAP sin resolver | **No** | — | **este informe los enumera** |

---

## 13. Physical Revalidation Checklist for CER

Sólo lo tocado por este delta. **No repetir el protocolo de campo completo.**

1. START odómetro → cámara → volver → **la tarea sigue abierta con la foto**
2. START odómetro → cámara → forzar recreación de la pestaña si se reproduce →
   **la tarea se reanuda**; si la foto ya estaba subida, aparece para confirmar
3. END odómetro → cámara → volver → **la tarea de cierre sigue abierta**
4. END odómetro → cámara → recreación → **se reanuda y la jornada NO se reabre**
5. Un día normal con ubicación precisa → el kilometraje sale igual que antes
6. Si es practicable, un entorno de mala señal → observar que la evidencia pobre
   **no se acepta**: o se recupera mejor, o acaba en Missing

En el 6, la consulta `L-10` del catálogo del MR !30 muestra los motivos, y
`recovery_accuracy_rejected` es el que confirma que F-1 está haciendo su trabajo.

---

## 14. Remaining Field Validation Items

1. Ejecutar G3, G4, G6, G7, G8 con la fixture ya corregida
2. Escribir y ejecutar O1–O10
3. Regresión limpia de RTE03–RTE06 y aislamiento de tenant
4. Decidir si el hallazgo del 409 (§4) merece su propia revalidación

---

## 15. Proposed Status

```
IMPLEMENTATION COMPLETE WITH PENDING VALIDATION
```

**No** se propone `READY FOR CER PHYSICAL REVALIDATION`, porque §11 deja tres
cosas sin evidencia y la instrucción exige que *todos* los criterios de
Development estén confirmados para ese estado.

**No** se declara `RTE06 CERTIFIED`: eso lo emite CER.

RTE07 **no** se ha empezado. RTE10-A01 **no** se ha empezado.

### Estimación de lo que falta

| Tarea | Horas-agente |
|---|---|
Estabilizar y ejecutar G3/G4/G6/G7/G8 | 2,0 |
Escribir y ejecutar O1–O10 | 5,0 |
Regresión limpia y cierre | 1,5 |
| **Subtotal** | **8,5** |

Margen **+50%** por automatización de navegador: **12,8 horas-agente.**
