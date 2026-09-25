# PROTOCOLO DE ESTIMACIÓN DE TIEMPO Y ESFUERZO

Dado que el agente no posee un reloj de tiempo real, **queda prohibido negarse a estimar o dar respuestas evasivas**. No tener reloj de pared no es excusa: se estima con telemetría y métricas proxy.

Cada vez que se solicite un informe de avance, una estimación de tiempo o un desglose de esfuerzo restante, se aplica el siguiente protocolo.

---

## 1. Métricas de entorno y velocidad (baseline)

Antes de estimar, recopilar datos **reales** de la ejecución, medidos y no recordados:

- **Líneas de código (LoC) generadas por componente** — `git show --stat`, `wc -l`.
- **Tokens consumidos o coste reportado** (`/cost`), cuando esté disponible.
- **Número de prompts/iteraciones completadas.**
- **Complejidad relativa por bloque:**
  - Dominio / lógica → **Alta**
  - Migraciones / boilerplate → **Media**
  - UI / pruebas E2E → **Alta fricción**

---

## 2. Fórmula de conversión de tiempo

Para convertir volumen en horas de desarrollo (*wall-clock equivalent*), calibrar con la velocidad histórica del tramo ya completado:

```
T_base = (LoC_restantes / LoC_completadas_tramo) * T_utilizado_en_ese_tramo
```

Si el usuario no ha expresado el tiempo real invertido en el tramo completado, usar estos coeficientes estándar de rendimiento de agente:

| Tipo de trabajo | Rendimiento |
|---|---|
| Código backend / dominio / migraciones | **150-200 LoC / hora-agente** (incluye refactor y tests) |
| Lógica de integración / OCR / flujos complejos | **80-100 LoC / hora-agente** |
| Automatización UI / navegador / pruebas E2E | **50-70 LoC / hora-agente** (alta variabilidad, *flaky tests*) |

---

## 3. Estructura obligatoria del informe de tiempos

Toda estimación se presenta en esta tabla. **Las cifras van en horas**, no en días: los días dependen de una jornada supuesta y ocultan el dato real.

| Tarea / Checkpoint | Estado | Volumen est. (LoC / Flujos) | Complejidad | Tiempo invertido / est. (horas-agente) |
|---|---|---|---|---|
| C1: Dominio base | Completado | ~1.400 LoC | Media | [registrar / calcular] |
| C2: … | Pendiente | ~1.400 LoC | Media | ~7 - 9 h |
| C3/C4: … | Pendiente | ~3.500 LoC | Alta | ~25 - 35 h |
| C5: Flujos UI | Pendiente | 7 flujos + regresión | Alta fricción | ~12 - 16 h |

Si además se pide una fecha, se puede derivar una jornada equivalente, **declarando siempre el supuesto** (por ejemplo, 4 h/día de interacción) y dejando claro que es modificable. La columna en horas no se sustituye por días: se añade.

---

## 4. Matriz de incertidumbre (buffer de riesgo)

Añadir automáticamente el margen de contingencia según la naturaleza del trabajo pendiente:

| Naturaleza | Margen |
|---|---|
| Tareas deterministas (migraciones, CRUD) | **+10%** |
| Integraciones de terceros / OCR / parsers | **+30%** |
| Automatización de navegador (E2E / Playwright) | **+50%** |

El margen se aplica y se declara, para que el interlocutor pueda discutir el coeficiente en vez de la cifra.
