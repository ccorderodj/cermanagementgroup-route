# RTE-MAIL-UNIFIED-01 V1.2 · B (CP2): plantillas estratégicas, destinatarios y generador del reporte

**Reporte B** · 16 de octubre de 2026
**Status B: COMPLETED WITH PENDING VALIDATION.**
- Las dos plantillas estratégicas, sus destinatarios y el generador **existen y están probados en local**.
- **La certificación con datos reales** sigue bloqueada por DP-NOTES, DP-WEEK, DP-TIMEZONE, DP-CUTOFF y DP-TEAM.
- **No se envía nada a nadie**, y ninguna nota real sale por correo.

## 1. Lo construido

| Pieza | Dónde | Qué hace |
|---|---|---|
| Dos tipos nuevos | `activityemails/content.py` | `strategic_midday_report` y `strategic_end_of_day_report`, con el **texto de V1.1** y el grupo `strategic` |
| Variables | ídem | Cuerpo: `manager_first_name`, `report_period_label`, `report_generated_at`, `per_person_report`; en el cierre, además, `team_weekly_summary` y `week_period_label`. Asunto: `manager_first_name` y `report_period_label` |
| Bloques obligatorios | ídem | `per_person_report` en los dos; `team_weekly_summary` en el cierre, **una vez y después** de las personas (si no, 422). El mediodía **no** admite `team_weekly_summary` |
| Generador | `activityemails/strategic.py` | Un bloque por persona: cabecera (nombre y cargo), *Activity Breakdown* del día, *Activity Details* y, en el cierre, *Weekly Activity Summary*. Después, **un** *Team Weekly Summary* |
| Datos de demostración | ídem (`_demo`) | Jerarquía ficticia de dos personas (Ana Ejemplo y Luis Muestra) con categorías, horas, una actividad en curso, coste «No disponible», notas ficticias y semana conciliada |
| Destinatarios de mandos | `service.list_strategic_recipients` / `update_strategic_recipient` | Solo mandos (CEO, COO, RM, `route_manager`) con cargo vigente y equipo. Dos interruptores apagados e independientes de los motivacionales, con la **cobertura real** |
| API | `GET /api/activity-emails/strategic-recipients`, `PUT /api/activity-emails/strategic-recipients/{id}` | Mismo permiso (`route.activityemails.manage`) y el alcance de quien administra |
| Pantalla | Activity Emails | Templates en dos grupos: **Motivational Emails** y **Strategic Activity Reports**. Recipients, en dos listas separadas (la de mandos con «Team in report: N»). Vista previa en letra monoespaciada |
| Migración | `0023_strategic_reports` | Amplía el CHECK de `template_type` y añade `strategic_midday_enabled` y `strategic_end_of_day_enabled` (`DEFAULT false`). **Conserva** plantillas y preferencias existentes; la bajada borra solo lo estratégico |

## 2. De dónde salen los números (sin recalcular)
- **Personas:** `organization.scope.alcance_administrativo(mando)`, el **mismo alcance** que Activity y Reports, tomando `alcance.actuales` sin el propio mando.
  - CEO: todo, Sales incluido. COO: su rama, sin Sales. RM: su subárbol.
  - Sin cargo de mando no hay equipo: el reporte no se convierte en la compañía entera.
- **Métricas:** `reports.dao.hechos` (una fila por viaje con su actividad) + `reports.service._metricas` / `_enriquecer` / `_combustible_por_jornada`. Son las mismas millas oficiales, tiempo de bloques terminados y coste estimado que la pantalla de Reports.
  - Sin coste: «No disponible», no 0.
  - Con coste parcial: «(parcial)».
  - Con actividad abierta: «(+ en curso)».
- **Detalle:** horas en la zona de la jornada con `reports.excel.reloj` (no UTC), duración y estado («Finalizada», «En curso», «Sin cierre registrado»).
- **Notas (DP-NOTES):** `nota_para_correo` **nunca** devuelve la nota real. Pone «Detalle no incluido en el correo» si la hay y «Sin notas registradas» si no.
- **Team Weekly Summary:**
  - personas **con actividad** en la semana, actividades, millas, tiempo («no es la jornada pagada») y coste;
  - las mismas categorías;
  - **es la suma de lo que se enseña en cada persona**, así que cuadra en el mismo correo;
  - las filas son una por viaje y cada persona sale una vez: no hay doble conteo.
- **Lo que no decide el generador:** el día, el corte del mediodía y el inicio de semana los **pasa quien llama**. El lunes es la regla de Activity, pendiente de DP-WEEK, y el reporte rotula sus fechas.

## 3. Criterios de V1.2 (§6) que cubre B

| # | Esperado → evidencia | Estado |
|---|---|---|
| 3 | Cuatro plantillas visibles, guardadas, previsualizadas y restaurables; editar las estratégicas no toca las motivacionales ni al revés → `test_cuatro_plantillas_y_las_estrategicas_aisladas`, `test_no_se_puede_quitar_ni_mover_el_resumen`, E2E | VALIDATED |
| 4 | Interruptores apagados, por tenant y jerarquía, auditados; CEO/COO/Sales y otro tenant → `test_mandos_apagados_con_su_cobertura_real` (CEO 8, COO 4 sin Sales, RM-A 2), `test_interruptores_estrategicos_independientes`, `test_quien_no_es_mando_o_no_tiene_equipo`, `test_un_coo_que_administra_solo_ve_a_su_rama` | VALIDATED |
| 5 | T3/T4 con dos personas; T4 con un Team Weekly Summary al final que cuadra; T3 sin él → `test_demo_*`, `test_el_resumen_del_equipo_cuadra_con_las_personas`, `test_vista_previa_ficticia` | VALIDATED |
| 6 | Sin datos reales ni notas no aprobadas → `test_alcance_del_reporte_y_notas_retenidas` (nota real en la base, ausente del texto) | VALIDATED |
| — | Generador con datos reales: alcance y conciliación → `test_alcance_del_reporte_y_notas_retenidas`, `test_resumen_del_equipo_cuadra_con_los_datos_reales` (22.5 millas = 12.0 + 7.5 + 3.0) | VALIDATED en local; **certificación real PENDING** de las DP |

## 4. Pruebas

| Lote | Resultado |
|---|---|
| `tests/test_strategic_report_content.py` + `tests/test_activity_email_content.py` | **42/42 PASS** |
| `tests/integration/test_strategic_reports.py` + `test_activity_emails.py` | **32/32 PASS** (10 nuevos) |
| E2E: grupo estratégico, vista previa T4, interruptor de mando, móvil sin desbordar | **PASS** (sección 5 del reporte C) |
| `alembic heads` | `0023_strategic_reports (head)`, uno |

**Hallazgos durante B:**
- **Tests desactualizados (CONFIRMED):** dos tests existentes comprobaban que solo había dos tipos de plantilla. Se actualizaron porque el producto ahora tiene cuatro.
- **Corregido en pantalla:** la ayuda de variables tenía `{{user_first_name}}` escrito a mano; ahora sale de la plantilla.
- **Vista previa ajustada:** las tablas se desalineaban con letra proporcional y la prosa se salía del diálogo. Ahora es monoespaciada y salta de línea.

## 5. Limitaciones y decisiones pendientes
- **Texto plano:** las tablas se alinean en clientes que muestran texto plano en monoespaciada. **Outlook puede usar letra proporcional** y desalinearlas. Un HTML con versión de texto se puede proponer en CP4 (**DECISION REQUIRED**).
- **Correos muy largos:** con equipos grandes el correo crece y no se recorta. Antes de CP4 hay que decidir un límite y un enlace autenticado a CER Route.
- **Bloquean el envío real:** DP-NOTES, DP-WEEK, DP-TIMEZONE, DP-CUTOFF, DP-TEAM y DP-SCOPE. Esta última está implementada como recomienda V1.1: todos los descendientes autorizados, sin el propio mando.

## 6. Git
Commit `c2dbad5`, junto con C, en `feature/mail-u01-cp2-cp3`.
