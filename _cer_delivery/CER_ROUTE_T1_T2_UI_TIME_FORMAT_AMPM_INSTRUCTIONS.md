# CER Route — Ajuste transversal de formato horario (AM/PM)

**Tipo:** Instrucción de ajuste de presentación para el agente de desarrollo  
**Proyecto:** CER Route  
**Checkpoint:** T-1/T-2 — Timezone & Business Day (ajuste de visualización dentro del checkpoint vigente)  
**Estado:** Autorizado por Product Owner para implementación, sujeto a verificación y certificación  
**Alcance:** Web administrativa y experiencia móvil / My Route

## 1. Context

La aplicación presenta actualmente horas con sufijos repetidos de zona horaria, por ejemplo:

`Viaje #1 · 5:41 PM UTC-04:00–6:02 PM UTC-04:00`

Esto sobrecarga visualmente las pantallas, especialmente en teléfonos. CER Route debe seguir interpretando correctamente los instantes según la **zona de referencia de la WorkSession** establecida por T-1/T-2; este cambio es **exclusivamente de presentación**.

**Decisión del Product Owner:** mostrar las horas operativas en formato de **12 horas con AM/PM, sin sufijos de zona horaria en las etiquetas visibles**. Conservar toda la evidencia temporal para integridad, consultas técnicas y auditoría.

## 2. Objective

Estandarizar la visualización de **todas las horas de reloj mostradas al usuario** en CER Route (Web y Mobile) para que sean legibles, consistentes y compactas, sin repetir `UTC-04:00`, `UTC−4`, `EST`, `EDT`, `CST`, `CDT`, zonas IANA ni otros sufijos de zona junto a cada hora.

## 3. Scope

1. Revisar los componentes compartidos y las pantallas que **renderizan horas de reloj** —tanto eventos como campos de horario, rangos y detalles— para aplicar la misma convención.
2. Incluir, según las superficies existentes en el repositorio: **My Route / Start Work / End Work**, Trips y Activities, **Today / Live**, **User Activity**, detalles e históricos, filtros con valores horarios, y reportes o resúmenes que exhiban horas al usuario.
3. Reutilizar o centralizar el formateador horario existente; evitar implementaciones independientes con resultados distintos según la pantalla.
4. Mantener la estructura, jerarquía, etiquetas, navegación y componentes aprobados. No agregar pantallas ni rediseñar.
5. Revisar también la representación de horas en los estados visibles que ya existen (por ejemplo, una hora dentro de una tarjeta, etiqueta, tooltip o modal existente). **No agregar elementos nuevos para mostrar la zona**.

**Límite:** esta instrucción aplica a **horas visibles en la UI**; no elimina campos de zona horaria en API, base de datos, auditoría estructurada o exportaciones de datos técnicos que requieran precisión temporal. No cambiar fechas, duraciones, nombres de campos de negocio ni valores almacenados.

## 4. Functional Requirements

### FR-01 — Hora individual

Mostrar cada hora en formato de 12 horas con minutos y sufijo `AM` o `PM`, sin zona horaria junto a la hora.

- Antes: `5:41 PM UTC-04:00`
- Después: **`5:41 PM`**

Usar una convención estable y evitar segundos salvo que una función existente los requiera explícitamente.

### FR-02 — Rangos de horas

Reducir repeticiones sin introducir ambigüedad:

- Mismo período: `5:41 PM–6:02 PM` → **`5:41–6:02 PM`**.
- Distinto período: **`11:50 AM–12:10 PM`** (no suprimir `AM` ni `PM` en ese caso).
- Madrugada: mostrar **`12:00 AM`** para medianoche y **`12:00 PM`** para mediodía.
- Si inicio y fin corresponden a **fechas locales diferentes**, conservar el indicador de fecha/día que ya exista o añadir la mínima aclaración textual necesaria para evitar confusión (por ejemplo, `(+1 día)`), sin reestructurar la pantalla.

Para el ejemplo reportado:

**Antes:** `Viaje #1 · 5:41 PM UTC-04:00–6:02 PM UTC-04:00`  
**Después:** `Viaje #1 · 5:41–6:02 PM`

### FR-03 — Zona temporal correcta, aunque no se muestre

La eliminación del sufijo **no autoriza** omitir la conversión horaria correcta.

- Interpretar los instantes en la **zona de referencia efectiva de la WorkSession** según el contrato temporal de T-1/T-2.
- Para una WorkSession que atraviesa estados o zonas, conservar la misma zona de referencia durante esa jornada.
- Nunca convertir por defecto a la zona del **navegador del administrador** cuando éste consulta datos de otro supervisor.
- No inferir abreviaturas IANA a partir de un offset histórico.
- Para registros históricos sin zona IANA, respetar las reglas de fallback y las limitaciones de precisión ya definidas en T-1/T-2; **no ocultar una incertidumbre real mediante una conversión inventada**. Si falta una fuente temporal fiable, conservar el comportamiento seguro del contrato, no fingir una hora exacta.

### FR-04 — Cobertura transversal

Buscar los puntos que formatean timestamps y horas de reloj, entre otros `toLocaleTimeString`, `Intl.DateTimeFormat`, `formatClock`, `formatSince` y etiquetas que concatenen `UTC`, `GMT` o abreviaturas de zona.

Actualizar los consumidores pertinentes con el formateador compartido. Esta búsqueda **no** es autorización para sustituir cadenas `UTC` o alterar serialización, lógica de negocio, logs, payloads, SQL, trazabilidad o componentes donde la zona forma parte del dato técnico y no de una etiqueta horaria visible.

### FR-05 — Duraciones y fechas

- Mantener las duraciones como duraciones (por ejemplo, `21 min`, `3 h 25 min`); **no añadir AM/PM**.
- No modificar la fecha operativa (`session_date`), agrupaciones o filtros por día/semana/mes/año.
- Preservar los indicadores de fecha cuando un rango cruza medianoche.
- El cálculo de duración debe seguir usando los instantes reales, nunca la resta ingenua de horas de reloj mostradas.

## 5. Out of Scope / Do Not Change

- No cambiar columnas ni ejecutar migraciones.
- No cambiar UTC, `timestamptz`, offsets, zona IANA almacenada o instante de ocurrencia.
- No modificar las reglas de zona operativa, DST, Today business day ni la sincronización offline de T-1/T-2.
- No alterar Start Work, End Work, odómetro, viajes, actividades ni kilometraje.
- No corregir jornadas olvidadas (P-2), ni mezclar H-3 o H-1.
- No agregar un selector de zona horaria ni nuevos controles administrativos como parte de este ajuste.
- No eliminar campos de zona/offset de contratos API por razones visuales.
- No cambiar arbitrariamente formatos de fecha, etiquetas de duración, datos de auditoría estructurados ni archivos de integración externa.

## 6. Acceptance Criteria

- **AC-01:** Las horas visibles en My Route / Trips / Activities, Today / Live, User Activity y demás superficies que renderizan horas muestran formato de 12 h con `AM`/`PM`, sin sufijos de zona por evento.
- **AC-02:** `Viaje #1 · 5:41 PM UTC-04:00–6:02 PM UTC-04:00` se presenta como `Viaje #1 · 5:41–6:02 PM`.
- **AC-03:** Los rangos que pasan de AM a PM, de PM a AM o cruzan fechas permanecen inequívocos.
- **AC-04:** Las horas de otro supervisor no cambian por la zona configurada en el dispositivo del administrador.
- **AC-05:** Los viajes entre zonas horarias siguen mostrándose en la zona de referencia de su WorkSession; las duraciones reales no cambian.
- **AC-06:** Las conversiones que atraviesan DST y los registros históricos siguen respetando las reglas temporales existentes; sin inventar instantes o zonas.
- **AC-07:** No se afectan reportes por fecha, `session_date`, cálculos de kilometraje, offline, auditoría, API ni base de datos.
- **AC-08:** No aparecen cambios de navegación, pantallas adicionales ni rediseños.
- **AC-09:** La representación es consistente en Desktop y Mobile, incluso tras recarga.

## 7. Tests Required

1. Prueba del formateador: hora individual, mismo AM/PM, cruce AM/PM, mediodía y medianoche.
2. Un viaje dentro de la jornada y otro que atraviesa medianoche; validar presentación de fecha cuando corresponda.
3. Usuario en Georgia y administrador consultando desde otra zona: la hora visible no depende del administrador.
4. WorkSession iniciada en Eastern cuyo supervisor se mueve a Central: el reporte usa la zona fija de la jornada y mantiene duración real.
5. Casos DST (salto hacia adelante y hora repetida) y fallback histórico según T-1/T-2.
6. Revisión de todas las vistas existentes que muestran horas, con evidencia Mobile y Desktop.
7. Pruebas de regresión focalizadas para Today, User Activity y My Route, sin tocar lógica de dominio.

## 8. Deliverables

Entregar **un solo ajuste dentro de T-1/T-2**, acompañado de:

- Relación de vistas/componentes revisados y modificados, indicando cobertura de las horas visibles.
- Ejemplos o capturas **antes/después** en Desktop y Mobile.
- Evidencia de pruebas y regresión, con PASS/FAIL/NOT RUN y limitaciones reales.
- Confirmación explícita de que no cambió el tratamiento temporal ni el dato almacenado.
- Commit SHA, rama/MR y MD breve de implementación.

**Criterio de cierre:** CER Route muestra horas limpias en AM/PM de forma uniforme, mientras conserva intacta la precisión temporal y la asignación de las jornadas a sus fechas correspondientes.
