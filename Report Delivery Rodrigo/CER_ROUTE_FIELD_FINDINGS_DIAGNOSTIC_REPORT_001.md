# CER Route — Field Findings Diagnostic — Report 001

**Fecha**: 2026-10-01
**Modo**: diagnóstico. **No se ha implementado ninguna corrección.**
**Instrucción**: `_cer_delivery/CER_ROUTE_FIELD_FINDINGS_DIAGNOSTIC_INSTRUCTIONS_001.md`
**Rama**: `feature/field-findings-diagnostic`

---

## 1. Executive Result

Los dos hallazgos de campo son **reales y de causa distinta**. No comparten
origen y no se corrigen juntos.

| Hallazgo | Clasificación | Bloquea certificación RTE06 |
|---|---|---|
| Odómetro: se pierde el contexto tras la foto | `NOT IMPLEMENTED / GAP` + `PENDING FIELD EVIDENCE` | **No**, pero deja una pantalla desorientadora |
| Recuperación de ubicación sin umbral de precisión | **`REGRESSION`** | **Sí, en mi opinión** |

El hallazgo que CER no reportó es el más serio. La **etapa 3 de la captura de
ubicación —la ventana de recuperación— no aplica ningún umbral de precisión**,
mientras las etapas 1 y 2 sí lo aplican. Un punto rechazado por impreciso en la
etapa 1 puede ser aceptado sin límite en la etapa 3, como `recovered`, que es un
nivel de evidencia de pleno derecho que el motor de kilometraje consume como
waypoint autoritativo.

Eso es exactamente lo que el §5 de la instrucción pide detectar: *"low-quality
evidence being treated as stronger evidence than it really is"*.

Sobre el odómetro: **ninguna evidencia se pierde por la navegación**. La foto se
sube al servidor en el propio manejador del input, antes de que cambie ninguna
pantalla. Lo que se pierde es el contexto visual.

---

## 2. Field Evidence Received

Lo recibido: la descripción de los dos hallazgos y capturas de Android que
muestran la experiencia de odómetro y el permiso de geolocalización con
**Precise** seleccionado.

**No se recibieron** identificadores de las filas de campo, así que §B1 no se
pudo ejecutar sobre datos reales. Para hacerlo, CER debe proporcionar:

- `company_id` del tenant usado;
- `username` o `user_id` del supervisor;
- `work_session.id`, o la fecha y hora aproximada de la jornada.

Con eso, las consultas `L-09`, `L-10`, `L-14` y `X-03` del catálogo entregado en
el MR !30 devuelven la distribución de niveles, los motivos de Missing, los
eventos en limbo y el retraso de sincronización de esa jornada concreta.

**No hay hardware Android disponible en Development**, así que §A5 se ejecuta por
lectura del código y queda una matriz explícita de lo que CER debe repetir en
dispositivo (§15.3).

---

## 3. START Odometer Reproduction

Trazado sobre el código, no sobre dispositivo.

**Ruta antes de abrir la cámara**: `RouteMyRoutePage`, fase `working`. El panel
de captura se muestra por el flag local `capturandoInicio`
([RouteMyRoutePage.tsx:168](app/components/react/pages/RouteMyRoutePage/ui/RouteMyRoutePage.tsx#L168)),
combinado en `capturandoOdometro` (línea 324) y renderizado en la línea 601.

**Apertura de cámara**: `<input type="file" accept="image/*" capture="environment">`
([OdometerCapture.tsx:139-153](app/components/react/features/RouteOdometer/ui/OdometerCapture.tsx#L139)).
No hay navegación: el navegador delega en la aplicación de cámara.

**Al volver**: `subirFoto`
([OdometerCapture.tsx:79-95](app/components/react/features/RouteOdometer/ui/OdometerCapture.tsx#L79))
sube la foto y cambia **solo estado local**: `setSugerencia`, `setLectura`,
`setTieneFoto(true)`. **No navega.** La única navegación del componente es
`onResolved()`, y se invoca en `confirmar()` (línea 102), después de confirmar la
lectura.

**El evento que sí ejecuta lógica al volver** está en la página, no en el
componente:

```tsx
useEffect(() => {
    reconcile();
    const alVolver = () => {
        if (document.visibilityState === 'visible') reconcile();
    };
    document.addEventListener('visibilitychange', alVolver);
```
[RouteMyRoutePage.tsx:260-270](app/components/react/pages/RouteMyRoutePage/ui/RouteMyRoutePage.tsx#L260)

`reconcile()` recalcula `view` desde el servidor. **No toca `capturandoInicio`**:
ese flag solo aparece en las líneas 168, 324 y 593. Así que un simple
`visibilitychange` **no debería cerrar el panel**.

**Conclusión de A1**: si la página únicamente recupera el foco, el estado
sobrevive y el supervisor debería seguir en el odómetro. El síntoma reportado
implica que la página **se está recreando**, no refocalizando.

---

## 4. END Odometer Reproduction

**Misma página, mismo componente, mismo mecanismo.** El flujo de cierre se
muestra por `revisandoCierre`
([RouteMyRoutePage.tsx:170](app/components/react/pages/RouteMyRoutePage/ui/RouteMyRoutePage.tsx#L170)),
otro `useState` sin persistencia, y renderiza el mismo `OdometerCapture`.

**Causa raíz compartida: sí.** No hay código específico de END que explique un
comportamiento distinto. Que CER observara lo mismo en los dos flujos es
coherente con una única causa.

La jornada **no ha terminado** cuando se pide la lectura de cierre: `End Work`
exige resolver la evidencia antes de escribir `ended_at`. La evidencia pendiente
se conserva correctamente en el servidor.

---

## 5. Root Cause

**El modo de captura del odómetro no se persiste en ningún sitio.**
`capturandoInicio` y `revisandoCierre` son `useState` puros. No hay
`sessionStorage`, ni URL, ni nada en el almacén que permita restaurarlos.

Mientras el proceso de la página viva, da igual. Si Android Chrome **descarta y
recrea la pestaña** —cosa habitual al abrir la cámara bajo presión de memoria—,
todo el estado de React se pierde:

1. `view` arranca en `{ phase: 'loading' }` (línea 155)
2. `reconcile()` consulta el servidor y calcula `working`
3. `capturandoInicio` arranca en `false`
4. Se renderiza el workbench, con el botón para registrar la lectura otra vez

Es exactamente el síntoma descrito: pantalla principal, tarea de odómetro sin
resolver.

**Clasificación: `NOT IMPLEMENTED / GAP`, no `REGRESSION`.** La restauración de
este estado nunca existió; no es algo que se rompiera.

**Lo que falta por confirmar — `PENDING FIELD EVIDENCE`**: si Android recrea la
página o solo la refocaliza. Son dos correcciones distintas y no quiero
proponer la equivocada. Ver §15.3.

---

## 6. OCR Runtime Status

**No hay OCR de producción cableado.** El lector activo es `NoSuggestionReader`
([ocr.py:50-67](app/routers_api/odometer/ocr.py#L50)), que es el valor por
defecto del módulo:

```python
_lector: OdometerReader = NoSuggestionReader()
```

Su docstring lo declara explícitamente: *"No es un hueco por rellenar. Es la
implementación honesta de 'este despliegue no tiene OCR'"*.

**Clasificación: corresponde a `RTE10-A01`**, no es una omisión accidental de
RTE06.

**Y no explica el hallazgo de navegación.** `suggest()` devuelve `None` y no
navega. En el cliente, una sugerencia ausente solo significa que `setLectura` no
se precarga ([OdometerCapture.tsx:88](app/components/react/features/RouteOdometer/ui/OdometerCapture.tsx#L88));
el panel se muestra igual con el campo vacío. **El problema de navegación existe
con OCR y sin él.**

---

## 7. Odometer Evidence Integrity

**Ninguna evidencia se pierde por el cambio de pantalla.** La foto se sube en el
propio `onChange` del input, antes de que nada navegue:

```
onChange → subirFoto → POST /odometer/sessions/{id}/{end}/photo → persistida
```

La fila de evidencia queda `pending` con su foto, y `Start Trip` sigue
correctamente bloqueado hasta que haya lectura confirmada. El supervisor puede
volver a entrar y confirmar sin repetir la foto.

**Hay un segundo modo de fallo, distinto y peor**: si Android destruye la página
**mientras la cámara está abierta**, el `onChange` nunca llega a ejecutarse y la
foto **no se sube**. No se corrompe nada —no hay a medias—, pero el supervisor
tiene que repetir la captura sin que nada le explique por qué.

`PENDING FIELD EVIDENCE`: cuál de los dos ocurrió en campo se distingue mirando
si existe `odometer_evidence.storage_key` para esa jornada.

---

## 8. Android Geolocation Evidence

**No ejecutable**: no se recibieron identificadores de las filas de campo (§2).

Lo que sí se puede afirmar sin ellas, por lectura de la implementación, está en
§9 y §10.

---

## 9. Location Quality Rules — As Built

Umbrales vigentes
([policies.py:72-77](app/core/platform/policies.py#L72)), **defendibles y no
certificados** por decisión expresa de §26:

| Parámetro | Valor |
|---|---|
`fresh_timeout_seconds` | 10 |
`fresh_max_accuracy_m` | **100** |
`cached_max_age_seconds` | 300 |
`cached_max_accuracy_m` | **500** |
`recovery_window_seconds` | 180 |
`sweeper_grace_seconds` | 120 |

### B3 — ¿`fresh` exige precisión? **Sí.**

```ts
const aceptable = precision === null
    || precision <= politica.freshMaxAccuracyM;
```
[location.ts:292](app/components/react/shared/lib/location/location.ts#L292)

Un punto recién capturado con más de 100 m **se rechaza como fresco**, se
registra el intento con su precisión y el flujo continúa a la etapa siguiente.
Regla correcta y aplicada.

### B4 — ¿`cached` exige las dos cosas? **Sí, ambas.**

```ts
const suficiente = dentroDeEdad && dentroDePrecision;
```
[location.ts:348](app/components/react/shared/lib/location/location.ts#L348)

Un punto antiguo pero preciso se rechaza; uno reciente pero impreciso también. La
edad original se conserva y viaja al servidor en `source_age_seconds`.

### B5 — Recuperación: **sin umbral alguno.**

```ts
const punto = await pedirPosicion({ enableHighAccuracy: true, ... });
await enviarPunto(eventKind, subject, 'recovered', punto, permiso);
```
[location.ts:386-401](app/components/react/shared/lib/location/location.ts#L386)

**No hay comprobación de precisión.** Lo que devuelva el navegador se acepta como
`recovered`.

La hora de captura enviada es la real de la recuperación, no la del evento, lo
cual es correcto y es el sentido del nivel.

### B6 — Veracidad de Missing

El camino escalonado es correcto: Missing solo se declara tras agotar las tres
etapas, y `permission_denied` corta en la etapa 1. La evidencia encolada
sobrevive al cierre del navegador (IndexedDB), y la correlación exacta por
`client_action_key` elimina la ambigüedad que antes convertía puntos válidos en
Missing.

**Privacidad, bien resuelta**: de un candidato rechazado se guardan **edad y
precisión, nunca las coordenadas**
([location.ts:360-366](app/components/react/shared/lib/location/location.ts#L360)).

### B2 — Precise vs Approximate: **la aplicación no puede distinguirlos.**

```ts
const estado = await navigator.permissions.query({ name: 'geolocation' });
return estado.state as EstadoDelPermiso;
```
[location.ts:107-117](app/components/react/shared/lib/location/location.ts#L107)

La API de permisos devuelve únicamente `granted` / `denied` / `prompt`. **No
expone el modo de precisión de Android.** La única señal disponible es la
`accuracy` medida.

Consecuencia directa: **los umbrales de precisión son la única defensa** contra
evidencia gruesa. Donde no hay umbral, no hay defensa.

### B7 — Consumo por el motor de kilometraje

`LocationFixesDAO.for_trip_waypoints()`
([dao.py:73](app/routers_api/location/dao.py#L73)) selecciona los puntos uniendo
`location_fix` con los eventos de dominio. Su único filtro sobre la tabla de
puntos es `f.company_id = :company_id`.

**No filtra por `evidence_level` ni por `accuracy_m`.** Cualquier punto aceptado
—de cualquier nivel y de cualquier precisión— se convierte en waypoint
autoritativo.

Las defensas que sí existen son posteriores y geométricas: distancia vial menor
que la recta, `segment_max_meters` 800 km, `implied_speed_max_kmh` 160, y el
`snap_radius_m` del motor.

---

## 10. Robustness Findings

### F-1 — La recuperación acepta cualquier precisión — `REGRESSION`

**Comportamiento actual**: etapas 1 y 2 aplican umbral; la 3 no.

**Debilidad observada**: un punto de, por ejemplo, 2.000 m de error se **rechaza**
como `fresh` (>100 m) y como `degraded_cached` (>500 m), y **se acepta** como
`recovered` sin límite. El nivel más lento de obtener acaba siendo el menos
exigente, que es lo contrario de lo razonable.

**Y conecta con B2**: en Android con permiso **Approximate**, todas las lecturas
son gruesas. El sistema las rechazaría dos veces y las aceptaría a la tercera.
Con `Precise` —lo que muestra la captura de CER— el riesgo es menor, pero el
supervisor puede cambiarlo en cualquier momento sin que la aplicación pueda
detectarlo.

**Impacto en datos/kilometraje**: alto. §B7 confirma que esos puntos entran como
waypoints. Las comprobaciones de plausibilidad son geométricas y **no atrapan un
error de 2 km a escala urbana**: la ruta resultante sigue siendo plausible.

**Impacto de seguridad/privacidad**: ninguno.

**Impacto en usuario**: ninguno. Corregirlo **no bloquea** ninguna acción: un
`recovered` rechazado desemboca en Missing, que es el camino ya aprobado.

**Requiere decisión de CER**: **sí** — qué umbral. Lo defendible técnicamente es
`cached_max_accuracy_m` (500 m): un punto recuperado no debería ser más laxo que
uno cacheado. Pero el número es materia de §26 y de calibración de campo.

**Esfuerzo**: ver §16.

### F-2 — Precisión desconocida tratada como aceptable — `TECHNICAL DEBT`

**Comportamiento actual**: `precision === null || precision <= umbral` en la
etapa 1 ([location.ts:292](app/components/react/shared/lib/location/location.ts#L292))
y `punto.accuracy === null || ...` en la 2 (línea 346). `accuracy` queda en
`null` cuando `Number.isFinite(coords.accuracy)` es falso (línea 129).

**Debilidad**: un punto cuya precisión no se pudo medir se acepta **en el nivel
más alto**. El sistema afirma una calidad que no verificó.

**Probabilidad**: baja. La especificación W3C declara `accuracy` como un double
no negativo obligatorio. No lo he medido en un navegador real y no voy a
suponerlo.

**Decisión de CER**: no. Es consistencia interna: desconocido debería degradar,
no aprobar.

### F-3 — El diagnóstico de un cacheado rechazado miente sobre el motivo — `TECHNICAL DEBT`

```ts
error_message: `cached point rejected: age ${edad}s`
```
[location.ts:371](app/components/react/shared/lib/location/location.ts#L371)

El mensaje habla **siempre de la edad**, aunque el rechazo haya sido por
precisión. Queda escrito en `missing_location_event.attempts`, que se conserva.
Quien lo lea dentro de un año creerá que el problema fue la antigüedad.

No afecta a los datos de kilometraje; afecta a quien calibre los umbrales con
datos de campo, que es justo lo que V-2 y V-5 van a hacer.

### F-4 — `fresh_max_accuracy_m` no está documentado con los demás

El docstring de `RouteLocationPolicy` explica el origen de cinco de los seis
parámetros y **salta `fresh_max_accuracy_m`**, que es el más restrictivo. No es
un defecto de código, pero sí la clase de omisión que lleva a que alguien lo
cambie sin entender qué protege.

---

## 11. Routing / Mileage Impact

| Caso | Comportamiento actual |
|---|---|
| Ubicación aceptada con baja precisión | **Entra como waypoint sin filtro.** Las comprobaciones son geométricas y no detectan errores de pocos km |
| Candidato cacheado rechazado | No entra. Solo quedan su edad y su precisión, sin coordenadas |
| Waypoint requerido Missing | El kilometraje termina en `not_calculable` con la razón concreta. Correcto |
| Rechazo por `snap_radius_m` | El motor responde `NoSegment`/`MAP_MATCHING_FAILURE` y el estado terminal es honesto |
| Plausibilidad | Vía más corta que la recta, 800 km máximo y 160 km/h implícitos |

**El hueco está en la primera fila**, y F-1 lo agrava: los puntos de peor calidad
del sistema son precisamente los que ninguna etapa acota.

---

## 12. Security / Privacy Impact

Ninguno de los hallazgos introduce riesgo de privacidad, y hay dos decisiones
bien tomadas que conviene reconocer:

- un candidato rechazado guarda edad y precisión, **nunca coordenadas**;
- la traza de auditoría registra tipo, sujeto, nivel y hora, y **no** latitud ni
  longitud — verificado con la consulta `D-02` del catálogo, que devuelve cero
  filas.

---

## 13. Expected vs Implemented

| Regla aprobada | Implementado |
|---|---|
| Acción operativa no bloqueante | **Sí.** `captureFor` no se espera con `await` y nunca lanza |
| Escalonado best-effort | **Sí**, tres etapas |
| `fresh` con umbral de precisión | **Sí**, 100 m |
| `cached` con edad y precisión | **Sí**, ambas |
| `recovered` con umbral | **No** ← F-1 |
| Missing tras agotar el camino | Sí |
| Evidencia sobrevive sin red | Sí, IndexedDB |
| Odómetro: foto + lectura confirmada | Sí |
| OCR asistivo, nunca autoritativo | Sí, y hoy no hay motor (RTE10-A01) |
| La tarea de odómetro sobrevive a la cámara | **No** ← §5 |

---

## 14. Classification

| # | Hallazgo | Clasificación |
|---|---|---|
| 1 | Contexto de odómetro perdido tras la foto | `NOT IMPLEMENTED / GAP` |
| 1b | Mecanismo exacto en Android | `PENDING FIELD EVIDENCE` |
| 2 | OCR de producción no cableado | `EXPECTED / BY DESIGN` → `RTE10-A01` |
| 3 | La acción continúa sin GPS | `EXPECTED / BY DESIGN` |
| F-1 | Recuperación sin umbral de precisión | **`REGRESSION`** |
| F-2 | Precisión desconocida aceptada | `TECHNICAL DEBT` |
| F-3 | Mensaje de rechazo engañoso | `TECHNICAL DEBT` |
| F-4 | Umbral sin documentar | `TECHNICAL DEBT` |
| — | Umbrales por calibrar en campo | `DECISION REQUIRED` (§26, V-2/V-5) |

---

## 15. Required Corrections

### 15.1 Obligatorio antes de certificar RTE06 — F-1

Aplicar un umbral de precisión a la etapa de recuperación, coherente con las
otras dos. Un punto que no lo supere sigue el camino ya aprobado: Missing.

**No cambia la regla de no bloqueo.** No introduce rastreo continuo, ni bloqueo
de GPS, ni avisos nuevos, ni proveedor nuevo.

**Requiere que CER fije el umbral.**

### 15.2 Recomendado, sin decisión de CER — F-2, F-3, F-4

Degradar en vez de aceptar cuando la precisión es desconocida; que el mensaje de
rechazo diga el motivo real; documentar `fresh_max_accuracy_m`.

### 15.3 Odómetro — **requiere evidencia de campo antes de elegir corrección**

No propongo la corrección todavía porque dos mecanismos distintos exigen
soluciones distintas, y no puedo distinguirlos sin dispositivo.

**Lo que CER debe repetir en Android**, en START y END:

| Caso | Qué anotar |
|---|---|
| Tomar foto y volver | ¿Se recarga la página (barra de progreso, parpadeo) o solo vuelve? |
| Retomar la foto | ¿Mismo comportamiento? |
| Foto sin sugerencia OCR | ¿Cambia algo? (no debería) |
| Lectura manual confirmada | ¿Se completa sin volver a la cámara? |
| Perder el foco durante la cámara | ¿Se pierde la foto o solo la pantalla? |

Y una comprobación en base de datos que lo resuelve sin ambigüedad: para esa
jornada, mirar si existe `odometer_evidence.storage_key`.

- **Con `storage_key`** → la foto se subió; solo se perdió el contexto visual
- **Sin `storage_key`** → la página murió con la cámara abierta y la foto nunca
  llegó a subirse

Son dos problemas distintos. El primero se arregla persistiendo el modo de
captura; el segundo, además, necesita que el supervisor sepa que debe repetirla.

---

## 16. Effort Estimate

Horas-agente de implementación. **No incluye tiempo de Git/MR** ni la
revalidación física de CER.

| Item | Mínimo | Probable | Alto | Incertidumbre principal |
|---|---:|---:|---:|---|
| F-1 umbral en recuperación | 1,5 | **2,5** | 4,0 | Qué hacer con el punto rechazado: ¿Missing directo o un intento más? |
| F-2 + F-3 + F-4 | 1,0 | **1,5** | 2,5 | Ninguna relevante |
| Odómetro: persistir el modo de captura | 2,0 | **3,5** | 7,0 | **Alta** — depende de §15.3. Si Android recrea la página, hay que restaurar desde el almacén; si no, basta con no cerrar el panel |
| Tests y regresión | 2,0 | **3,0** | 5,0 | Lo de odómetro necesita simular el ciclo de vida del navegador |
| **Total implementación** | **6,5** | **10,5** | **18,5** | |

Margen de riesgo: **+50%** en lo del odómetro (automatización de navegador),
**+10%** en lo de geolocalización (determinista).

**Revalidación física de CER**, separada y no comparable: la matriz de §15.3 son
10 casos (5 × START/END), más una jornada completa para muestrear la distribución
de niveles de evidencia con la corrección F-1 puesta.

---

## 17. Impact on RTE06 / RTE10-A01 / RTE07

| Alcance | Impacto |
|---|---|
| RTE04 Odómetro | Sí — el modo de captura es suyo |
| RTE05 Workbench | Sí — `RouteMyRoutePage` decide la pantalla |
| RTE06 Field Validation | Sí — F-1 es de la tubería de evidencia |
| **Certificación final RTE06** | **Sí** — ver Q1 y Q4 |
| RTE10-A01 OCR | No cambia su alcance. Se confirma que sigue pendiente |
| RTE07 | Ninguno. **No se ha empezado** |

---

## 18. Decisions Required from CER

**D-1. Umbral de precisión para la recuperación.** ¿500 m, como el cacheado? ¿Otro
valor? §26 impide que Development lo fije.

**D-2. Qué hacer con un punto recuperado rechazado.** Lo coherente es Missing con
un motivo nuevo —algo como `recovery_accuracy_rejected`—, que sería el **séptimo**
motivo del catálogo. Añadirlo toca una restricción de base.

**D-3. Alcance de la corrección del odómetro**, después de §15.3.

**D-4. ¿Se certifica RTE06 antes o después de estas correcciones?**

---

## 19. Recommendation

**Mi recomendación: no certificar RTE06 hasta corregir F-1.**

El resto de la tubería de evidencia está construida con cuidado —tres etapas,
umbrales aplicados, Missing veraz, privacidad bien resuelta, correlación exacta—
y precisamente por eso el hueco de la etapa 3 destaca: es la única puerta sin
cerradura de una casa con todas las demás cerradas. Y es la que más importa,
porque §B2 demuestra que **los umbrales de precisión son la única defensa que la
aplicación tiene** contra evidencia gruesa: el navegador no le dice si el permiso
es Precise o Approximate.

El kilometraje oficial es un dato que §27 y §28 obligan a conservar para siempre.
Un waypoint de ±2 km produce una distancia que parece razonable, pasa todas las
comprobaciones geométricas y queda escrita como hecho.

**Es un delta pequeño** (§16: 2,5 horas probables), no reabre ningún checkpoint y
no cambia la regla de no bloqueo.

Lo del odómetro **no bloquearía la certificación en mi opinión**: ninguna
evidencia se pierde por la navegación y el control de `Start Trip` sigue en pie.
Es una corrección de experiencia que merece hacerse bien, con la evidencia de
campo de §15.3 en la mano, en vez de adivinando el mecanismo.

---

## STOP

Diagnóstico entregado. **No se ha implementado ninguna corrección. No se ha
empezado RTE07.**

A la espera de D-1 a D-4.
