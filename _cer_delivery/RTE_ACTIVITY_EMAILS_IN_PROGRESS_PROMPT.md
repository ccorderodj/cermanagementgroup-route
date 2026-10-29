# CER Route — Reportes de actividad: incluir actividades en curso

**Tipo:** instrucción de cambio puntual para agente de desarrollo. **Prioridad:** corrección funcional. **No ampliar alcance.**

## Contexto y objetivo
Hoy los reportes por correo de **mediodía** y **fin de día** muestran principalmente actividades finalizadas y omiten actividades que el usuario **ya inició y aún no terminó**. Corregir ambos reportes para incluirlas explícitamente como **"In Progress / En curso"**, sin presentarlas como completadas.

## Instrucción
1. Ubica los constructores/consultas y plantillas **existentes** de los reportes por correo (estratégicos y del usuario, donde corresponda). Reutilízalos; no crees reportes, endpoints, jobs, plantillas ni modelos paralelos.
2. Para cada reporte determina el **instante de corte que ya tiene definido** y calcula el estado histórico de cada actividad **a ese instante**, no según su estado al momento de generar/reintentar el correo:
   - **Completed:** iniciada y finalizada hasta el corte.
   - **In Progress:** iniciada hasta el corte, sin finalización válida hasta ese instante, mientras la jornada siga abierta.
   - Si la jornada ya cerró y la actividad quedó sin finalizar, **no afirmar que sigue en ejecución**; identificarla como **"Started / Not Completed"** (o equivalente coherente con los estados existentes).
   - Actividades que comiencen después del corte: **excluirlas**. Respetar cancelaciones y otras transiciones reales si existen; no inferir actividad a partir del propósito del viaje.
3. Presentar las actividades iniciadas dentro del **mismo listado/detalle actual**, con estado visible, hora de inicio y demás datos existentes. Evitar duplicados y no asignar hora de finalización ni duración definitiva a las actividades abiertas.
4. Si existen conteos o totales, **separar completadas de en curso/no finalizadas**. No sumar actividades abiertas como completadas ni alterar cálculos históricos o acumulados sin justificación.
5. **Preservar** horarios y disparadores existentes (reporte estratégico al mediodía y a las 7:00 p. m.; motivacional de mediodía y correo de fin de jornada del usuario), destinatarios, RBAC/jerarquía, alcance por tenant, cortes de zona horaria, diseño general, envío, reenvío, idempotencia y auditoría.

## Criterios de aceptación / pruebas
- Actividad iniciada 11:40 y terminada 12:15: reporte de 12:00 => **In Progress**; reporte posterior al cierre => **Completed**.
- Actividad iniciada después de 12:00: **no aparece** en el reporte de mediodía, incluso si el correo se genera o reenvía después.
- Actividad abierta al corte de 7:00 p. m. con jornada abierta: **In Progress**.
- Jornada cerrada con actividad no finalizada: **Started / Not Completed**, sin inventar cierre.
- Actividad completada: mantiene el comportamiento actual; ninguna se duplica ni se convierte erróneamente en abierta.
- Verificar reportes del usuario y estratégicos donde aplica, vistas previas, envíos manuales/reenvíos y pruebas de permisos/tenants.

## Entrega
Implementar el cambio mínimo y devolver un **MD breve** con archivos modificados, comparación Expected vs Implemented, pruebas ejecutadas/resultados y riesgos pendientes. **No modificar** el motor de actividades, itinerarios, GPS, millaje, routing, programación de correos ni otras funcionalidades.
