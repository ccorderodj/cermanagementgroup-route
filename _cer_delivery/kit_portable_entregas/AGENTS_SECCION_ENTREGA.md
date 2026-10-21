## Modo de trabajo y entregas ({{PROYECTO}})

Estas reglas complementan las de arquitectura del proyecto; no las sustituyen.
Detalle en `{{RUTA_KIT}}/`.

### 1. Ejecutar es entregar
Cuando se pide **ejecutar** algo (una instrucción, un arreglo, un ajuste), la
entrega forma parte del trabajo y **no se pide permiso** para hacerla:

1. **Rama dedicada, antes de escribir código.** Partir de `{{RAMA_BASE}}`
   actualizada. Comprobar la rama actual primero: tras cada fusión el checkout
   vuelve a `{{RAMA_BASE}}`. **Nunca** commitear en `{{RAMA_BASE}}` ni en `main`.
2. **Validar** (§4) hasta tener la evidencia exigida.
3. **Commit, push y MR** con `{{RUTA_KIT}}/PROCEDIMIENTO_GIT_Y_MR.md`.
4. **Reporte** en `{{CARPETA_REPORTES}}` con
   `{{RUTA_KIT}}/PLANTILLA_REPORTE_ENTREGA.md`. Un hito sin reporte es media
   entrega: quien decide no lee el código.
5. **No fusionar nunca.** El MR queda para revisión y certificación.

Excepciones: «solo diagnóstico», «no toques nada» o «no hagas cambios» significa
**solo lectura**. Nada de código, datos, migraciones ni despliegues.

### 2. Reportar durante la ejecución, no solo al final
- **Avisar en cada hito real:** fin de fase, fin de un lote de tests, migración,
  build, fallo, corrección, decisión humana necesaria. No narrar cada comando.
- **Evidencia concreta:** `24/24 PASS`, `exit 0`, `1745 passed · 1 failed`. Nunca
  «parece que funciona».
- **Lo no ejecutado se marca** `NOT RUN`, `PENDING` o `NOT APPLICABLE`. **La
  evidencia ausente nunca se convierte en PASS.**
- **`IMPLEMENTED` no es `VALIDATED`:** validado exige la evidencia nombrada.
- **Causas etiquetadas:** `CONFIRMED`, `LIKELY` o `UNVERIFIED`. Una suposición
  no se presenta como hecho.
- **Los errores propios se reportan** aunque ya estén corregidos: qué falló y
  que después pasó.
- **Hallazgos fuera del alcance:** se dicen cuando aparecen, con su acción
  operativa.
- **Local ≠ compartido:** cada afirmación dice a qué entorno aplica.
- **Fallos que ya existían:** se identifican por nombre y se separan de los
  nuevos. Si hay duda, se comprueba en `{{RAMA_BASE}}` sin el cambio.

### 3. Estimar siempre, en horas
Prohibido negarse a estimar. Se mide el volumen real (`git diff --shortstat`,
LoC) y se convierte con estos coeficientes:

| Tipo de trabajo | LoC por hora-agente |
|---|---|
| Backend, dominio, migraciones | 150–200 |
| Integraciones, flujos complejos | 80–100 |
| UI, navegador, E2E | 50–70 |

Se añade el margen de riesgo: **+10 %** determinista, **+30 %** terceros, **+50 %**
navegador. Va en una tabla: tarea · estado · volumen · horas-agente. A «¿cuánto
queda?» se responde con el avance medido (%, tests, hora prevista de fin).

### 4. Validación antes de entregar
Escalar de lo dirigido a lo amplio: tests del cambio, luego los relacionados, y
la regresión completa si el cambio toca algo compartido.

```bash
# Ajustar a este proyecto:
<comando de tests dirigidos>
<comando de typecheck / lint>
<comando de build>
<comando de regresión completa>
```

Las migraciones se prueban subiendo, bajando y volviendo a subir, con un solo
head. Un dato de negocio ambiguo no se interpreta en silencio: se reporta.

### 5. Cierre de cada iteración
Toda iteración en la que se ejecutó algo termina con:

1. **Status:** `COMPLETED`, `COMPLETED WITH PENDING ITEMS` o `BLOCKED`.
2. **Qué cambió y por qué.**
3. **Validación**, con resultados reales.
4. **Hallazgos**, con la causa etiquetada.
5. **Estimación** de lo que falta.
6. **Git:** rama, commits, push, MR (número y URL) y si está fusionado.
7. **Acción operativa** pendiente en otros entornos.
8. **Siguiente paso, sin empezarlo.** Reportar no autoriza alcance nuevo.

### 6. Resumen para {{DESTINATARIO}}
«Hazme el resumen para {{DESTINATARIO}}» →
`{{RUTA_KIT}}/PLANTILLA_RESUMEN_DIRECTIVO.md`, **siempre con la misma estructura**.
Antes de escribirlo, copiar la tabla «Estado del proyecto» del resumen anterior
y actualizarla. {{DESTINATARIO}} compara entregas entre sí.

### 7. Forma de responder
- **Una recomendación principal,** con razón, riesgo y trade-off. No cinco
  opciones equivalentes.
- **No re-explicar** el contexto ya establecido ni reabrir decisiones cerradas
  sin evidencia nueva.
- **Separar** hecho, inferencia, hipótesis y recomendación cuando haya duda real.
- **Seguridad:** no leer `.env`, no pedir ni escribir secretos en chat,
  documentos ni capturas. Nada de producción sin autorización expresa.
