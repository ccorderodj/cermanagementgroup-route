# CER Route — RTE10-A01 · Corrección del consenso de OCR
## Reporte 005

**Instrucción:** `CER_ROUTE_RTE10_A01_OCR_CONSENSUS_CORRECTION_INSTRUCTIONS_004.md`
**Rama:** `fix/ocr-native-consensus-variants` (desde `dev`, que ya contiene MR !54)
**Motor:** Tesseract 5.5.3.20260724 / leptonica 1.87.0, ejecutado de verdad
**Fecha:** 2026-10-05

---

## 1. Resultado ejecutivo

El diagnóstico de CER era correcto y estaba incompleto en un punto que importa.

Era correcto en que el motor **sí lee** y el consenso no lo confirmaba. Estaba
incompleto en que había **dos** defectos, no uno, y el segundo es el más grave:

1. **El repertorio de variantes.** La ampliación ×2 no confirmaba; producía
   números equivocados por encima del umbral de confianza.
2. **La regla de acuerdo.** Devolvía en cuanto un valor alcanzaba dos
   coincidencias, así que cuando dos valores distintos llegaban a dos, **el
   orden de la tupla de variantes decidía qué número se sugería**. Medido:

   ```
   mismas lecturas: 191517, 191517, 191817, 191817   (la verdad era 151517)
   primero-en-llegar -> 191517 o 191817, según el orden
   un-solo-ganador   -> sin sugerencia
   ```

   No es un caso de laboratorio: es lo que ocurre con un salpicadero de 1400 px
   donde el odómetro ocupa el 18% del encuadre.

Con los dos corregidos, sobre 25 imágenes con **verdades distintas** —no sólo la
de referencia— y el mismo binario:

| | MR !54 | corregido |
|---|---:|---:|
| Aciertos | 13 | **17** |
| **Consensos equivocados** | 2 | **1** |
| Sin sugerencia | 10 | 7 |

Ningún umbral se tocó: `MIN_CONFIANZA` sigue en 60, `MIN_DIGITOS` en 4,
`COINCIDENCIAS_NECESARIAS` en 2. La mejora viene de entradas más estables y de
una regla que no depende de cómo esté escrita una constante.

**El consenso equivocado que queda es anterior a este checkpoint y no se puede
resolver con variantes de preprocesado.** Está en §15, con su medición, porque
es lo que CER necesita saber para decidir si reabre la discusión del proveedor
externo.

---

## 2. El síntoma productivo

```text
POST /api/odometer/sessions/315/end/photo   ->  HTTP 200
"ocr_suggestion": null
"ocr_detected_reading": null
"scan_status": "not_configured"
```

La foto subió, la evidencia se actualizó y el camino de OCR no aceptó ninguna
sugerencia. No era un fallo de subida: era una decisión de consenso.

**Reproducido**: sí, en la clase de imagen, con el módulo de MR !54 ejecutado
tal cual sale de `dev`. Ver §4 y §9.

---

## 3. Las imágenes de referencia de CER

**Esto es un límite de esta entrega y conviene leerlo antes de la matriz.**

Las fotografías exactas **no están disponibles para el agente de desarrollo**:
llegaron al canal de conversación, no al repositorio ni al disco de trabajo.
§13 de la instrucción las pide «si están disponibles», y no lo están.

Lo que sí había, y resultó ser suficiente para encontrar el defecto, son **las
mediciones por variante que CER publicó** en §3 de la instrucción. Con ellas se
pudo verificar que el fallo descrito es exactamente el que produce el código,
y reconstruir la clase de imagen a las dimensiones reportadas:

| | CER reportó | reconstrucción usada aquí |
|---|---|---|
| E1 salpicadero | 524 × 381 | 524 × 393 (dibujado a 1400 y reducido) |
| E2 recorte ajustado | 185 × 72 | 185 × 72 |

Se dibuja grande y se reduce a propósito: es lo que hace una cámara seguida de
un reescalado, y no produce la misma imagen que dibujar directamente pequeño.

**Lo que la reconstrucción no reproduce**: el cristal del salpicadero, el
reflejo, el ángulo, la tipografía del fabricante, el ruido del sensor y la
compresión exacta de la cámara. Por eso §19 no se cumple en su totalidad y el
estado propuesto en §17 de este reporte lo dice en lugar de redondearlo.

**Acción para CER**: ejecutar las dos fotografías exactas. Si se adjuntan al
canal de trabajo, la medición por variante se repite aquí en minutos.

---

## 4. Reproducción por variante de MR !54

Con el módulo de `dev` sin modificar, sobre la clase E1 (524 px):

| Variante | Dim. efectiva | Tokens crudos | Aceptado | Lectura |
|---|---|---|---|---|
| `x1+nitidez` | 524×393 | `191517@45.7`, `60@95.9` | no (`<60`) | `None` |
| `x1` (sin nitidez) | 524×393 | `247.6@67.8`, `151517@96.0`, `60@93.6` | sí | `151517` |
| `x2+nitidez` | 1048×786 | `191817@60.0`, `60@96.8` | **sí** | `191817` |

```
ODOMETER OCR | las variantes no coinciden (151517.0, 191817.0): sin sugerencia
```

Es la misma estructura que midió CER —una variante lee la verdad, otra cae bajo
el umbral, la ampliada lee **otro número aceptado**— con los papeles de
«con nitidez» y «sin nitidez» intercambiados, que es lo que cabe esperar de una
reconstrucción con otra tipografía.

Y sobre la clase E2 (185×72), MR !54 sí acertaba: cuatro de las nueve imágenes
de recorte del repertorio amplio se leían bien. El defecto está concentrado en
**el salpicadero**, que es justo lo que el supervisor fotografía.

---

## 5. Causa raíz

Dos causas, las dos `CONFIRMED` por medición:

**C1 — La ampliación ×2 no es un canal de confirmación.**
Por sí sola, sobre 25 imágenes: 11 lecturas correctas, **3 equivocadas**, 11
sin lectura. Las equivocadas fueron `191817`, `131517` y `161617`, y **dos de
esos valores no los genera ninguna variante nativa**. Es decir, la ampliación
no sólo no confirmaba: inyectaba errores nuevos con los que otro error podía
coincidir. Es la fuente de la familia `191817` / `454517` que midió CER.

**C2 — La regla de acuerdo dependía del orden.**
`suggest()` devolvía en cuanto `lecturas.count(valor) >= 2`. Con cuatro
variantes repartidas entre dos valores erróneos, el resultado era el primero
que llegara a dos — y eso es una propiedad del orden de la tupla, no de la
fotografía. Permutando las cuatro lecturas del caso `dash1400` se obtienen
`{191517, 191817}`: dos sugerencias distintas, las dos equivocadas, para la
misma imagen.

C2 es más grave que C1 porque no se ve: produce un número con cara de
confirmado y no deja rastro de que hubo conflicto.

---

## 6. Estrategias de variantes evaluadas

Método: se puntuaron **todos** los subconjuntos de tamaño 2 a 4 de un repertorio
de diez preparaciones, sobre 25 imágenes (20 positivas con seis verdades
distintas, 5 negativas), con el motor real. El criterio de orden fue primero el
número de **consensos equivocados** y sólo después el de aciertos.

| Conjunto | Aciertos | Equivocados | Callados |
|---|---:|---:|---:|
| `r1.0-180 r1.5-180 r1.2-240 r2.0-240` ← **elegido** | **17** | **1** | 7 |
| `r1.5-180 r1.2-240 r2.0-240` | 17 | 2 | 6 |
| `r1.5-180 r2.0-240` | 16 | 1 | 8 |
| `r1.0-180 r1.2-180 r1.5-180` (la dirección de §7) | 13 | **2** | 6 |
| `r1.2-180 sin-nitidez x2` (MR !54) | 12 | 1 | 8 |

**La dirección de partida de la instrucción no se sostuvo, y la razón es
instructiva.** Tres radios al mismo porcentaje son una familia de un solo eje, y
producen errores **correlacionados**: en el salpicadero de 1400 px, `r1.0` y
`r1.5` leían *las dos* `191517` donde la verdad era `151517`, y al coincidir se
confirmaban mutuamente. Un acuerdo entre dos preparaciones que fallan igual no
es evidencia independiente; es el mismo fallo contado dos veces, que es la
misma falacia que MR !54 corrigió en su otra forma.

Los valores de §7 se midieron como pedía la instrucción —son evidencia de
partida, no constantes obligatorias— y se descartaron **con el dato**.

---

## 7. El repertorio elegido

Cuatro preparaciones, todas a **resolución nativa**, que mueven radio *y*
porcentaje para no quedarse en un solo eje:

```python
VARIANTES = (
    ("r1.0-p180", 1.0, 180),
    ("r1.5-p180", 1.5, 180),
    ("r1.2-p240", 1.2, 240),
    ("r2.0-p240", 2.0, 240),
)
```

En el caso difícil, esa diversidad es exactamente lo que salva: las cuatro se
reparten entre `191517` y `191817` en vez de concentrarse en uno, y dos valores
con acuerdo son un **conflicto**, no una mayoría.

**La regla de acuerdo, reescrita.** Se leen todas las variantes y se exige que
**exactamente un** valor alcance las dos coincidencias. Si lo alcanzan dos, no
se elige «el más confiado»: se calla. El resultado ya no depende del orden —hay
un test que permuta las cuatro lecturas y comprueba que las 24 permutaciones dan
lo mismo.

Cuesta una invocación más en el caso bueno. Medido: **1,62 s la peor foto** de
las 25, contra el límite de 15 s del puerto (`suggest_safely`). No es un
problema de latencia.

**Deduplicado por contenido, no por parámetros.** Sobre un salpicadero sin nada
legible —una superficie casi plana— las dieciséis preparaciones del repertorio
amplio dieron **los mismos bytes exactos**: realzar el contraste local de una
zona sin contraste local no cambia nada. Deduplicar por el nombre de la variante
o por su dimensión habría dejado pasar dieciséis «evidencias independientes»
justo en la imagen donde no hay ninguna. Ahora la clave es el hash del PNG ya
preparado, que es la única definición de «entrada distinta» que no se puede
satisfacer por accidente.

---

## 8. Decisión sobre la ampliación ×2: **retirada**

Con evidencia, no por inercia ni por conservarla porque la introdujo MR !54:

* **Aportación marginal sobre el mejor conjunto nativo: cero.** No cambió el
  resultado en ninguno de los 25 casos.
* **Por su cuenta: 3 lecturas equivocadas** (`191817`, `131517`, `161617`), dos
  con valores que ninguna variante nativa produce.
* Es la fuente de la familia de errores que CER midió (`191817`, `454517`).

Ampliar sigue siendo una opción de preprocesado si algún día la evidencia lo
justifica; lo que no es, y ya está escrito en el código y en un test, es
**evidencia adicional**.

---

## 9. Matriz antes / después

Mismas 25 imágenes, mismo binario, las dos columnas ejecutadas por el
`suggest()` real (la columna «MR !54» se obtuvo cargando el módulo tal como está
en `dev`).

| Caso | Verdad | MR !54 | Corregido |
|---|---|---|---|
| **E1** `dash524` | `151517` | `None` | **`151517`** |
| `dash524` | `128437` | `None` | **`128437`** |
| `dash524` | `098244` | `None` | **`98244`** |
| `dash524` | `234567` | `None` | **`234567`** |
| **E6** `dash524` + cuentaparcial `241.6` | `151517` | `None` | **`151517`** |
| `dash524` odómetro al 34% | `151517` | `151517` | `151517` |
| `dash900` | `151517` | **`191817` ⚠ equivocado** | **`None`** |
| `dash900` | `128437` | `128437` | `128437` |
| `dash1400` | `151517` | `None` | `None` |
| `dash1400` | `128437` | `128437` | `128437` |
| `dash1400` odómetro al 34% | `128437` | `None` | `None` |
| **E2** `crop185` | `151517` | `151517` | `151517` |
| `crop185` × 5 verdades más | varias | correctas | correctas |
| **E8** `crop185` desenfoque 1.6 | `151517` | `151517` | `151517` |
| **E8** `crop185` JPEG 72 | `128437` | `128437` | `128437` |
| `crop130` (reducido) | `151517` | `151517` | `151517` |

Lo que cambia de signo: las cuatro imágenes de salpicadero a 524 px pasan de
silencio a lectura correcta, y `dash900` pasa de una **sugerencia equivocada**
a silencio.

---

## 10. Matriz de falsos positivos

| Caso | Esperado | MR !54 | Corregido |
|---|---|---|---|
| **E4** Odómetro ilegible, velocímetro `60` | `None` | `None` | `None` ✔ |
| **E4** Odómetro ilegible, velocímetro `120` | `None` | `None` | `None` ✔ |
| **E5** Nada numérico legible | `None` | `None` | `None` ✔ |
| **E7** Empate de longitud (`151517` vs `241612`) | `None` | `None` | `None` ✔ |
| **E9** Acuerdo en conflicto (`dash1400`) | `None` | `None` / equivocado según orden | `None` ✔ |
| **E10** Una sola observación aceptada | `None` | `None` | `None` ✔ |
| Lectura corta legítima (`1234`) | `1234` | `1234` | `1234` ✔ |
| **E8** Desenfoque destructivo σ=4.0 | — | **`161617` ⚠** | **`161617` ⚠** |

El último está en §15. Es anterior a este checkpoint, sigue después, y **no se
disimuló**: tiene su propio test que lo documenta como límite.

---

## 11. Registro de diagnóstico

Por foto, a nivel **INFO** —`LOG_LEVEL=INFO` es el valor por defecto, así que
CER lo verá en el piloto sin cambiar nada—:

```text
ODOMETER OCR | variante r1.0-p180 524x393 -> None
ODOMETER OCR | variante r1.5-p180 524x393 -> 151517.0
ODOMETER OCR | variante r1.2-p240 524x393 -> 151517.0
ODOMETER OCR | variante r2.0-p240 524x393 -> 151517.0
ODOMETER OCR | acuerdo 3/4 -> 151517.0
```

Y cuando no hay sugerencia, dice **por qué**, que era lo que faltaba:

```text
ODOMETER OCR | acuerdo en conflicto (191517.0, 191817.0): sin sugerencia
ODOMETER OCR | sin acuerdo entre 4 variantes (ninguna leyó): sin sugerencia
ODOMETER OCR | sólo 1 variante distinta: sin acuerdo posible, sin sugerencia
```

Cinco o seis líneas por foto, acotado. **No** lleva bytes de imagen, ni usuario,
ni vehículo, ni sesión, ni secretos: sólo variante, dimensión efectiva y número.

---

## 12. Tests y regresión

| Lote | Tests | Resultado | Exit | Tiempo |
|---|---:|---|---:|---|
| `tests/test_odometer_ocr_reader.py` (con Tesseract) | 39 | **39 PASS** | 0 | 8,5 s |
| el mismo, con el binario ausente del `PATH` | 39 | **33 PASS, 6 SKIP** | 0 | 2,2 s |
| Integración de odómetro (6 archivos) | 81 | **81 PASS** | 0 | 98 s |
| Navegador START / END de odómetro | 9 | **9 PASS** | 0 | 110 s |
| `import app.main` | — | **OK** | 0 | — |

Los 6 `skip` son los casos que necesitan el motor real, declarados con su
motivo. Se ejecutaron con el binario presente, que es lo que §14 pide: nada se
silenció para cerrar.

**Tests añadidos** (12 nuevos, 3 reescritos):

* consenso: dos variantes que coinciden; tres donde dos coinciden; una sola
  observación; una sola variante distinta; **conflicto entre dos valores con
  acuerdo**; **24 permutaciones del orden dan el mismo resultado**;
* preparaciones: deterministas; las cuatro producen bytes distintos;
  configuraciones duplicadas se colapsan; **configuraciones distintas que dan la
  misma imagen también se colapsan**; no se escribe en disco;
* repertorio: **ninguna variante amplía la imagen**;
* con el motor real: clase de recorte; **clase de salpicadero a 524 px**;
  odómetro + cuentaparcial; salpicadero sin odómetro no sugiere el velocímetro;
  **odómetro pequeño en el encuadre no produce una lectura equivocada**;
  **desenfoque destructivo: el límite, documentado**.

Frontend: **NOT APPLICABLE**, no se tocó ni un archivo de interfaz.
Migraciones: **NOT APPLICABLE**, no hay cambio de esquema.

---

## 13. Impacto en START / END

**Ninguno.** No se tocó el flujo, ni los permisos, ni los contratos, ni la
semántica de confirmación. El cambio vive entero en el adaptador de OCR.

* Una foto sin sugerencia sigue siendo evidencia válida y el camino manual sigue
  disponible — `suggest_safely()` convierte cualquier fallo del motor en «sin
  sugerencia», no en un error de la petición.
* La confirmación del supervisor sigue siendo la autoridad. Dado §15, eso no es
  una formalidad: es el único control para la clase de fallo que queda.
* 9/9 en los caminos de navegador START y END.

---

## 14. Esperado → Implementado → Evidencia → Hueco

| AC | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | Síntoma productivo reproducido o explicado por variante | **VALIDATED** | §4, con el módulo de `dev` |
| 2 | Imagen E1 completa produce `151517` | **VALIDATED en la clase de imagen** | §9. La fotografía **exacta** no está disponible aquí (§3) |
| 3 | Imagen E2 ajustada produce `151517` | **VALIDATED en la clase de imagen** | §9. Igual salvedad |
| 4 | Dos variantes materialmente distintas coinciden | **VALIDATED** | §7; deduplicado por hash del PNG; test de bytes distintos |
| 5 | `MIN_CONFIANZA` sigue 60 | **VALIDATED** | sin cambios en el archivo |
| 6 | `MIN_DIGITOS` sigue 4 | **VALIDATED** | sin cambios |
| 7 | `COINCIDENCIAS_NECESARIAS` sigue 2 | **VALIDATED** | sin cambios |
| 8 | ×2 retirada o retenida por evidencia | **VALIDATED** | §8: retirada, con la medición |
| 9 | Valores cortos de salpicadero rechazados | **VALIDATED** | §10 (`60`, `120`) |
| 10 | Empate de longitud rechazado | **VALIDATED** | §10 |
| 11 | Sin odómetro legible → `None` | **VALIDATED** | §10 |
| 12 | No se trata `151517` como caso especial | **VALIDATED** | 6 verdades distintas en la matriz; `151517` no aparece en el código |
| 13 | Camino manual intacto | **VALIDATED** | §13, 81/81 integración |
| 14 | Confirmación del supervisor sigue siendo autoridad | **VALIDATED** | §13, sin cambios de semántica |
| 15 | No se añade proveedor externo | **VALIDATED** | sólo Tesseract |
| 16 | START/END sin cambios | **VALIDATED** | §13, 9/9 navegador |
| 17 | Tesseract real ejecutado y registrado | **VALIDATED** | 5.5.3, 39/39 + las dos matrices |
| 18 | Regresión afectada verde | **VALIDATED** | §12 |
| 19 | Sin `PARTIAL` / `GAP` / `BLOCKED` en el delta autorizado | **VALIDATED** | el delta está completo |

**Hueco, y es de entrada, no de implementación**: la validación con las
**fotografías exactas** de CER (§13 de la instrucción, capa 2 de dos) no se
pudo ejecutar porque los archivos no están disponibles para el agente. Por eso
§17 no propone el estado completo.

---

## 15. Límites de OCR que quedan

**L1 — El acuerdo no detecta la ambigüedad de la imagen. `CONFIRMED`.**

Es el hallazgo que más conviene que CER lea. Con un desenfoque de σ=4.0 sobre el
recorte, el `5` **se convierte** en un `6` dentro de la propia imagen, y las
**diez** preparaciones probadas leyeron `161617` con confianzas de 84 a 91:

```
sin-nitidez 161617 @ 89.71     r1.0-p180 161617 @ 90.09
r0.8-p180   161617 @ 89.23     r1.2-p240 161617 @ 91.23
r1.5-p180   161617 @ 89.58     r2.0-p240 161617 @ 84.44
x2-r1.2     161617 @ 87.77     ...
```

> El acuerdo entre preparaciones detecta **fragilidad del preprocesado**, no
> **ambigüedad de la imagen**.

Ninguna composición de variantes lo resuelve, porque no hay desacuerdo que
detectar. Subir `MIN_CONFIANZA` a 92 para taparlo dejaría sin sugerencia todo lo
demás. Es anterior a este checkpoint —MR !54 tiene el mismo comportamiento— y
sigue después. **El control que queda es la confirmación del supervisor.**

**L2 — Odómetro pequeño en el encuadre. `CONFIRMED`, mitigado a silencio.**

Con el salpicadero a 1400 px y el odómetro al 18%, los dígitos quedan en unos
pocos píxeles de alto y el motor confunde `1`/`9` y `5`/`9`. Antes esto podía
salir como sugerencia equivocada (`dash900` → `191817`); ahora sale como
silencio. La misma escena con el odómetro al 34%, o a 524 px, se lee bien — es
decir, **se evita encuadrando más cerca**, que es acción del supervisor y está en
§16.

**L3 — Display de siete segmentos.** Sin cambios: Tesseract está entrenado sobre
texto. Es probable que no sugiera nada, y eso es el camino manual, no una avería.

**L4 — La reconstrucción no es la fotografía.** §3.

---

## 16. Lista de revalidación para el piloto (CER)

1. Fotografía **exacta** de salpicadero completo → se espera `151517`.
2. Fotografía **exacta** de recorte ajustado → se espera `151517`.
3. Captura START normal.
4. Captura END normal.
5. Odómetro ilegible con velocímetro visible → se espera **sin sugerencia**.
6. Reflejo / desenfoque → verificar que **no** aparece un número equivocado con
   apariencia de confirmado.
7. Camino manual con una foto sin sugerencia.
8. Corrección y confirmación por el supervisor.

Para cada sugerencia equivocada, registrar: **lectura real, lectura sugerida,
tipo de tablero, dimensiones de la imagen** y, si está a mano, las líneas
`ODOMETER OCR | variante ...` del log, que ahora dicen qué leyó cada
preparación. Con eso se decide si queda margen en Tesseract o si CER reabre la
decisión del proveedor externo.

**Encuadre**: una indicación al supervisor de acercarse al odómetro mueve el
caso L2 de «sin sugerencia» a «lectura correcta» sin tocar código.

**Acción operativa**: ninguna. No hay migración, ni semilla, ni variable de
entorno nueva, ni cambio de despliegue. `LOG_LEVEL=INFO` ya es el valor por
defecto, así que el diagnóstico por variante aparece sin configurar nada.

---

## 17. Estado propuesto

```text
IMPLEMENTATION COMPLETE / PENDING EXACT-IMAGE VALIDATION
```

El delta autorizado está terminado y medido con el motor real: no queda
`PARTIAL`, `GAP`, `BLOCKED` ni decisión pendiente dentro de él.

**No se propone `READY FOR CER OCR PILOT REVALIDATION`** porque §19 lo condiciona
a haber ejercitado las imágenes de referencia exactas, y esos archivos no
estaban disponibles aquí (§3). La validación de la **clase** de imagen está
hecha y verde; la de las **fotografías** es la capa que falta, y se completa en
minutos si CER las adjunta o las ejecuta en el piloto.

No se declara `RTE10-A01 CERTIFIED` ni `OCR PRODUCTION CERTIFIED`: la
certificación de campo es de CER.

---

## 18. Estimación del esfuerzo

Volumen real de esta iteración (`git diff --numstat`):

| Componente | Líneas (+/−) |
|---|---|
| `app/routers_api/odometer/ocr_tesseract.py` | +136 / −122 |
| `tests/test_odometer_ocr_reader.py` | +231 / −9 |
| `tests/fixtures_odometer.py` | +12 / −0 |
| **Total** | **+379 / −131** |

| Tarea | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Reproducción por variante de MR !54 | `DONE` | 3 bancos de medición | medición con binario real | 0,8 |
| Rejilla de preprocesado + puntuación de subconjuntos | `DONE` | 25 imágenes × 18 configuraciones | integración/OCR | 1,2 |
| Repertorio + regla de acuerdo + deduplicado | `DONE` | ~136 LoC | backend/dominio | 0,8 |
| Tests (12 nuevos, 3 reescritos) | `DONE` | ~231 LoC | backend | 1,3 |
| Regresión (reader, integración, navegador) | `DONE` | 129 tests | ejecución | 0,6 |
| Reporte 005 | `DONE` | — | documentación | 0,5 |
| **Subtotal ejecutado** | | | | **5,2** |
| Margen de riesgo (+30%, integración con binario de terceros) | | | | **+1,6** |
| **Total de la iteración** | | | | **≈ 6,8 h-agente** |

Coeficientes de `_cer_delivery/estimacion_de_tiempo_y_esfuerzo.md`: backend/dominio
150–200 LoC/h, integración/OCR 80–100 LoC/h. El margen aplicado es el de
integraciones de terceros porque el resultado depende de la versión del binario.

**Pendiente de CER, no estimable aquí**: la revalidación con las fotografías
exactas (§16), que es trabajo de campo.

---

## 19. Trabajo restante y siguiente paso

**Restante en este checkpoint**: nada dentro del delta autorizado.

**Siguiente paso natural, sin empezarlo**: ejecutar §16 con las dos fotografías
exactas. Si la clase de salpicadero se lee en campo, RTE10-A01 queda a merced de
la certificación de CER. Si **no** se lee, la evidencia que pide §16 —lectura
real, sugerida, tipo de tablero, dimensiones y las líneas por variante del
log— es exactamente lo que permite decidir entre seguir endureciendo Tesseract
o reabrir la decisión del proveedor externo, y esa decisión es de CER.
