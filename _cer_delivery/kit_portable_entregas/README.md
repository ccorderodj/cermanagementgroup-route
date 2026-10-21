# Kit portable de entregas

Las reglas de trabajo de CER Route —cómo se ejecuta, cómo se reporta, cómo se
entrega a Git y cómo se resume para dirección— empaquetadas para usarlas en
**otro proyecto**.

## Qué hay aquí

| Archivo | Para qué |
|---|---|
| `AGENTS_SECCION_ENTREGA.md` | El bloque que se pega en el `AGENTS.md` (o `CLAUDE.md`) del otro proyecto. Es lo que el agente lee siempre |
| `PROCEDIMIENTO_GIT_Y_MR.md` | Ramas, commits, push y MR (GitLab sin `glab`, o GitHub con `gh`). Nunca fusionar |
| `PLANTILLA_REPORTE_ENTREGA.md` | El reporte técnico de cada entrega, que va en la carpeta de reportes |
| `PLANTILLA_RESUMEN_DIRECTIVO.md` | El resumen para dirección («hazme el resumen para Rodrigo»), en clave de negocio y con formato fijo |
| `referencia/recomendaciones_eficientes_y_ejecutables.md` | Cómo responder y recomendar: una recomendación principal, economía de tokens |
| `referencia/progreso_y_reporte_de_ejecucion.md` | Hitos durante la ejecución, IMPLEMENTED ≠ VALIDATED, evidencia concreta |
| `referencia/estimacion_de_tiempo_y_esfuerzo.md` | Estimar en horas-agente con coeficientes y margen de riesgo |

Los tres de `referencia/` son copias literales de los de CER Route. Hablan de
CER Route en sus ejemplos; las reglas valen igual.

## Cómo instalarlo en otro proyecto (5 minutos)

1. **Copiar la carpeta** `kit_portable_entregas/` al otro repositorio, por
   ejemplo en `docs/entregas/` o `_delivery/`.
2. **Sustituir los marcadores** en los cuatro archivos de la raíz del kit:

   | Marcador | Ejemplo en CER Route | Qué poner |
   |---|---|---|
   | `{{PROYECTO}}` | CER Route | Nombre del producto |
   | `{{RAMA_BASE}}` | `dev` | La rama a la que van los MR |
   | `{{CARPETA_REPORTES}}` | `Report Delivery Rodrigo/` | Dónde se guardan los reportes |
   | `{{DESTINATARIO}}` | Rodrigo | Quién decide y lee en clave de negocio |
   | `{{PLATAFORMA_GIT}}` | GitLab | GitLab o GitHub |
   | `{{RUTA_KIT}}` | `_cer_delivery/kit_portable_entregas` | Dónde dejaste el kit |

3. **Pegar** el contenido de `AGENTS_SECCION_ENTREGA.md` al final del
   `AGENTS.md` del otro proyecto, o crear `AGENTS.md` con él si no existe.
   Claude Code lee `AGENTS.md` y `CLAUDE.md` al empezar cada sesión. Si el
   proyecto usa `CLAUDE.md`, basta con una línea `@AGENTS.md` en él.
4. **Crear la carpeta de reportes** (`{{CARPETA_REPORTES}}`) vacía.
5. **Ajustar los comandos de validación** de la sección «Validación antes de
   entregar» del bloque pegado: tests, typecheck, lint y build reales del otro
   proyecto.

## Lo que el kit no trae (a propósito)

- **Las reglas de arquitectura de CER Route** (multi-tenant, RBAC, páginas…):
  son del producto, no del modo de trabajar.
- **La memoria del agente.** Lo que el agente aprendió en CER Route vive en su
  memoria de **ese** proyecto y no se traslada sola. Por eso todo lo
  importante (formato del resumen, mecánica del MR, «entregar sin preguntar»)
  está escrito aquí, en archivos del repositorio.

## Frases que activan cada cosa

| Lo que dices | Lo que hace el agente |
|---|---|
| «Ejecuta estas instrucciones @archivo.md» | Implementa, valida, **commit + push + MR + reporte** sin pedir permiso. No fusiona |
| «hazme el resumen para {{DESTINATARIO}}» | Escribe el resumen con `PLANTILLA_RESUMEN_DIRECTIVO.md`, actualizando la tabla de estado del resumen anterior |
| «cuánto tiempo queda» | Estimación en horas-agente con el método de `referencia/estimacion_de_tiempo_y_esfuerzo.md` |
| «no toques nada, solo diagnóstico» | Solo lectura: ni código, ni datos, ni commits de código |
