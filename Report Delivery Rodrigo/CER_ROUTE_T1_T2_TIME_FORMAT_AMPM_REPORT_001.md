# CER Route · T-1/T-2 · Ajuste de formato horario AM/PM

**Reporte 001** · 9–10 de octubre de 2026
**Instrucción:** `CER_ROUTE_T1_T2_UI_TIME_FORMAT_AMPM_INSTRUCTIONS.md`
**Rama:** `feature/t1-t2-time-format-ampm`

---

## Status

`PENDING VALIDATION`

Implementado y validado con pruebas del formateador, E2E en escritorio y móvil
y regresión. Queda la validación de CER en dispositivos reales.

---

## 1 · Qué cambia, en una línea

Las horas se muestran en **12 h con AM/PM y sin sufijo de zona**, y los
tramos se compactan. **La zona de la jornada sigue gobernando la conversión**:
sólo deja de imprimirse.

| Antes | Después |
|---|---|
| `ABC Manufacturing · 5:41 PM UTC-04:00–6:02 PM UTC-04:00` | `ABC Manufacturing · 5:41–6:02 PM` |
| Today: `5:17 PM` / `EDT` | `5:17 PM` |
| My Route en un teléfono en español: `14:11` | `2:11 PM` |
| Excepciones: hora del navegador del administrador | `Oct 9, 8:49 PM`, la de la jornada |

---

## 2 · Confirmación: no cambió el tratamiento temporal ni el dato

- **Ninguna migración, ninguna columna, ningún valor almacenado.**
- La conversión sigue saliendo de la **zona efectiva de la jornada** (T-1/T-2):
  ni del navegador del administrador ni del idioma del dispositivo.
- `session_date`, agrupaciones, filtros, duraciones, kilometraje, offline,
  auditoría: **sin tocar**. Las duraciones siguen calculándose sobre
  instantes reales (`spanBetween`), no restando horas de reloj.
- **El API no pierde ningún campo.** Gana dos, de sólo lectura, en la cola de
  excepciones de odómetro (§4.2).

---

## 3 · Las reglas, en un solo formateador

`shared/lib/utils/utils.ts` — `formatEventClock`, `eventClockParts`,
`formatClockRange` y `formatEventDateTime`. **Todas** las pantallas pasan por
aquí: no queda ninguna implementación propia con otro resultado.

| Caso | Resultado |
|---|---|
| Hora individual | `5:41 PM` |
| Tramo, mismo periodo | `5:41–6:02 PM` |
| Tramo, distinto periodo | `11:50 AM–12:10 PM` |
| Mediodía / medianoche | `12:00 PM` / `12:00 AM` |
| Tramo que cruza medianoche | `11:50 PM–12:10 AM (+1 day)` |
| Estado que empezó otro día (Today) | `Oct 8, 11:30 PM` (indicador que ya existía) |
| Fecha y hora (excepciones) | `Oct 9, 5:41 PM` |
| **Sin ninguna fuente horaria** (ni zona ni desfase) | `9:41 PM UTC` |

`en-US` y `hour12` explícitos: un navegador en español o en inglés británico
ya no impone las 24 h.

### La única marca que se conserva, y por qué

Si una jornada **no registró ni zona ni desfase**, no hay forma de saber su hora
local. Mostrar la hora a secas sería fingirla; FR-03 lo prohíbe expresamente
(«no ocultar una incertidumbre real mediante una conversión inventada»). En ese
caso —sólo en ese— la hora se lee en UTC y lo dice. Las jornadas históricas con
desfase **no** lo llevan: el desfase es una fuente válida para su hora.

### Limitación inherente · la hora repetida de otoño

El 1 de noviembre la hora de 1:00 a 2:00 ocurre dos veces. Un tramo de 1:30 EDT
a 1:30 EST se lee `1:30–1:30 AM`: sin sufijo de zona, no hay forma de
distinguirlas. La **duración real** aparece al lado en la tarjeta (`1h 00m`) y
deshace la duda. Es el coste de quitar la zona; si el PO prefiere marcar la zona
**sólo** en ese caso, es un cambio de pocas líneas.

---

## 4 · Superficies revisadas

### 4.1 · Modificadas

| Superficie | Antes | Ahora |
|---|---|---|
| **Today / Live** (tabla, detalle, lista y detalle móvil) | hora + `EDT` / `UTC-04:00` | hora sola; la segunda línea sólo para *time zone not determined* |
| **User Activity**, cabecera de tarjeta | dos horas con sufijo | tramo compacto; no se parte entre líneas |
| **My Route**, *Working since* | `toLocaleTimeString` del navegador | zona de la jornada, AM/PM |
| **My Route**, parada (*Working here since*) | igual | igual que arriba |
| **Excepciones de odómetro** (admin) | zona e idioma del administrador | zona de la jornada, AM/PM |

### 4.2 · El único cambio de backend

La cola de excepciones de odómetro no traía la zona de la jornada, así que la
hora sólo podía mostrarse en la del administrador (contra AC-04). Se añadieron
`time_zone` y `utc_offset_minutes` a cada fila: **lectura**, aditivos, con un
`LEFT JOIN` a la jornada. Ningún otro contrato cambia.

### 4.3 · Revisadas y no modificadas

| Superficie | Por qué no |
|---|---|
| Duraciones (`spanBetween`, `formatDuration`) | son duraciones; FR-05 |
| Fechas sin hora (supervisores, `formatDate`) | no son horas de reloj |
| Ajustes de plataforma y solicitudes de permisos de seguridad | administración de la plataforma, no horas operativas de CER Route; su zona es la de quien mira por diseño |
| Calendario (`shadcn`) | componente de fecha |

---

## 5 · Validación

### 5.1 · El formateador · 64/64 PASS

El **módulo real** `utils.ts`, transpilado con el TypeScript del proyecto y
ejecutado en Node —no una copia—, con el navegador del administrador en cuatro
zonas: **Nueva York, Chicago, Madrid y Tokio**. 16 casos en cada una: hora
individual, histórica con desfase, sin fuente, el ejemplo del reporte, cruce
AM→PM, mediodía, medianoche, cruce de medianoche, DST de otoño (las dos
1:30) y de primavera (1:59 → 3:00), fecha y hora, jornada nocturna, y Este
→ Centro con la zona fija de la jornada.

No hay ejecutor de pruebas de JavaScript en el proyecto (ni Jest ni Vitest), así
que esto es un arnés de verificación y **no** queda como prueba versionada.

### 5.2 · Navegador · 6/6 PASS

`test_time_format_ampm_browser.py` (nueva), con navegadores deliberadamente
incómodos:

| Prueba | Navegador | Comprueba |
|---|---|---|
| User Activity, escritorio y móvil | **Tokio, en español** | **AC-02 literal**: `ABC Manufacturing · 5:41–6:02 PM`, sin `UTC` |
| My Route, móvil | Este, **en español** | `Working since` en AM/PM; ninguna hora en 24 h en la página |
| Excepciones, escritorio | **Madrid**, en español | la hora es la de la jornada del Este |

Y `test_t1_t2_time_zones_browser.py`, **actualizada**: exigía la abreviatura en
el navegador del Centro y ahora exige que **ninguna** vista la lleve; la misma
hora con el navegador en el Este y en el Centro sigue comprobándose.

**Un defecto propio, encontrado por la captura y corregido:** en móvil el tramo
se partía —`5:41–6:02` arriba y `PM` sola abajo—. Ahora no se parte.

Capturas en `var/screenshots/time-format/` y `var/screenshots/t1-t2/`.

### 5.3 · Antes y después

**Después:** las capturas de §5.2, en escritorio y móvil.

**Antes:** no se regeneraron con el bundle anterior (`NOT RUN`). La evidencia
del «antes» son las capturas del propio PO —Today con `UTC-04:00` y `EDT`— y
la captura `today-escritorio-centro` del reporte T-1/T-2 (`5:17 PM` / `EDT`),
que la ejecución de hoy sobrescribió con la versión nueva.

### 5.4 · Comprobaciones

```
npm run typecheck           0 errores
npm run lint:ts             0 errores
npm run build:prod          compilado (2 avisos de tamaño, preexistentes)
uv run python -c "import app.main"   OK
```

### 5.5 · Regresión · suite completa · exit 1

```
uv run pytest        53 min 50 s

1263 PASS · 6 FAILED · 1 ERROR · 15 skipped
```

| Resultado | Qué es |
|---|---|
| 1 FAILED `test_provisioning_alignment` | preexistente: 14 frente a 12 capacidades, espera decisión de CER |
| 5 FAILED de navegador (`rte06` ubicación sin conexión y precisión de recuperación) | **los mismos 5 que ya fallan en `dev`**; sin relación con este ajuste |
| 1 ERROR `test_route_notes_migration_safety::test_m4…` | ver §5.6 |
| 15 skipped | motor de rutas real no configurado aquí; igual que siempre |

**Ningún fallo nuevo.** Today, User Activity, My Route, *Keep working*, H-2,
R-1, T-1/T-2 y el ajuste AM/PM, en verde.

### 5.6 · El error de la migración: interferencia externa · `CONFIRMED`, origen `UNVERIFIED`

Al terminar `test_m4…`, Alembic no encontró la revisión **`f5c5fde65b15`**
en la base de pruebas de ese worker. **Esa revisión no existe en este
repositorio** —todas se llaman `0001_…` a `0015_…`— ni en ningún proyecto de
`CesarProjects/python/CER`, y nada en este código escribe `alembic_version` con
un valor así.

Lo que sí se observó: este PostgreSQL lo comparten varios proyectos hermanos, la
base de pruebas se llama `cer_time_test` (nombre heredado de otro proyecto), y
**había una conexión activa a ella a las 01:47, con esta suite ya terminada**.
Lo más probable es que otro proceso usara las mismas bases de pruebas durante la
ejecución.

- Repetida sola, la prueba pasa: **7/7**.
- No tiene relación con el ajuste AM/PM (frontend y una lectura de la cola).
- **Acción recomendada** (no se hace aquí): dar a la base de pruebas de CER
  Route un nombre propio (`cer_route_test`) para que ningún otro proyecto la
  comparta. Es un cambio de configuración local, no de código.

---

## 6 · Acceptance Criteria

| AC | Estado | Evidencia |
|---|---|---|
| AC-01 · 12 h AM/PM sin sufijo en todas las superficies | **VALIDATED** | §4.1, §5.2 |
| AC-02 · el ejemplo del reporte | **VALIDATED** | E2E literal, escritorio y móvil |
| AC-03 · AM→PM, PM→AM y cruces de fecha inequívocos | **VALIDATED**, con la limitación de §3 | §5.1 |
| AC-04 · no depende de la zona del administrador | **VALIDATED** | 4 zonas en §5.1; Tokio y Madrid en §5.2 |
| AC-05 · zona fija de la jornada; duraciones intactas | **VALIDATED** | §5.1 (Este → Centro); duraciones sin tocar |
| AC-06 · DST y históricos sin inventar | **VALIDATED** | §5.1; sin fuente → `UTC` explícito |
| AC-07 · reportes, `session_date`, kilometraje, offline, auditoría, API, base | **VALIDATED** | §2; regresión §5.5 sin fallos nuevos |
| AC-08 · sin navegación ni pantallas nuevas | **VALIDATED** | ningún componente nuevo |
| AC-09 · consistente en escritorio y móvil, tras recarga | **VALIDATED** | §5.2; el formato no depende de estado del navegador |

---

## 7 · Estimación

| Tarea | Volumen | Complejidad | Horas-agente |
|---|---|---|---|
| Inventario de superficies | — | — | 0,5 |
| Formateador compartido y rangos | ~160 LoC | UI | 2,0 |
| Cinco superficies y la cola de excepciones | ~110 LoC | UI / determinista | 1,5 |
| Arnés del formateador (64 casos) | — | — | 0,8 |
| E2E nueva y actualizada, con capturas | ~240 LoC | navegador | 2,5 |
| Regresión, reporte y entrega | — | — | 1,5 |
| **Total** | **≈ 420 líneas** | | **≈ 8,8 h** |

---

## 8 · Git

| | |
|---|---|
| Rama | `feature/t1-t2-time-format-ampm` |
| Base | `dev` en `aebedbd` (T-1/T-2 ya integrado) |
| Commit | `68a3c5e` |
| MR | **!82** · https://gitlab.com/cermanagementgroup/cermanagementgroup-route/-/merge_requests/82 |
| Árbol | limpio |
| Fusionado | **No.** Sujeto a certificación |
| Despliegue | servidor y bundle; **sin migraciones**. Tras desplegar, recargar la aplicación |
