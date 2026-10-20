# RTE-MAIL-CLOSE-01 · CP1 — Corte, roster y horarios

**Fecha:** 2026-10-20 · **Rama:** `feature/rte-mail-close-01` · **Commit:** `aff295d` · **Entorno de la evidencia:** local
**Estado:** IMPLEMENTED + VALIDATED en local · NOT DEPLOYED

## Expected → Implemented → Evidence → Gap

| Expected | Implemented | Evidence (local) | Gap / Impact |
|---|---|---|---|
| T1/T3 a las 12:00 **locales** del destinatario | Corte fijo a las 12:00 en la zona del destinatario | `test_mediodia_local_en_zonas_y_cambios_de_horario` (NY, Chicago, dos cambios de horario de 2026) PASS | — |
| Actividad 11:30–13:26 no sale «Finalizada» a las 12:00, ni con duración, eventos futuros o millas posteriores | El corte trabaja sobre una **copia** de los datos tal como estaban: actividad abierta = «En curso» sin duración; viaje sin llegar = sin millas; lo que empezó después no existe. Los registros originales no se tocan | `test_actividad_que_cruza_el_mediodia_no_sale_finalizada`, `test_al_corte_recorta_una_copia_sin_tocar_el_original` PASS | La actividad abierta cuenta como evento «(+ en curso)», sin duración. Se ve por la hora real de cada evento: un registro sin conexión con hora anterior a las 12:00 que se sincroniza más tarde entra en un reporte que se **regenere** después (Send now), no en el que salió a las 12:00 |
| Minutos coherentes (ejemplo del 19/10) | Duraciones de **reloj**: minutos entre las horas que se enseñan (11:30–1:26 = 1h 56m). Detalle, desglose y totales suman lo mismo | `test_los_totales_cuadran_en_minutos_de_reloj` PASS | Cambia respecto a Reports, que redondea los segundos reales. Solo afecta a los correos |
| T2 = End Work + **20** min; reapertura aplaza; dos sesiones; medianoche | Sin cambio de regla (ya era +20); cubierto con tests | `test_t2_a_los_20_minutos_con_dos_sesiones` (+19 no, +20 sí), `test_t2_de_una_jornada_que_cruza_la_medianoche` (envío real por el despacho), `test_fin_de_jornada…aplazado_si_reabre` PASS | — |
| T4 a las **19:00** fijas: ni antes aunque cierre el equipo, ni después por jornadas abiertas | `CIERRE_ESTRATEGICO = 19:00` locales; foto de las 19:00. Se retira `MAIL_STRATEGIC_CUTOFF` | `test_t4_no_se_adelanta…` (18:59 no, 19:00 sí), `test_t4_sale_a_las_19_con_jornadas_abiertas_y_sin_inicio`, `test_cierre_estrategico_a_las_19…` (verano/invierno, LA) PASS | — |
| T3/T4 con **todas** las personas activas del alcance, con o sin jornada; nunca «Ausente» | `strategic.roster`: personas activas (pertenencia y cuenta). Por persona: inicio y fin reales de WorkSession, estado («Sin registro de inicio al corte», «En curso», «Finalizada») y jornada registrada (suma de sesiones). Executive Snapshot arriba | Mismo test de T4: SUP-A Finalizada 7h, SUP-C En curso 9h aunque cerró a las 19:30, OSM-A sin inicio; snapshot `4 \| 2 \| 1 \| 1` PASS | Una plantilla ya guardada sin `{{executive_snapshot}}` lo recibe al principio del bloque por persona, sin editar su texto |
| CEO = admin/superadmin, solo su tenant, con Sales; COO sin Sales | Destinatarios estratégicos: mandos **más** `owner`/`admin`. Un administrador recibe toda la jerarquía vigente de **su** compañía | `test_admin_representa_al_ceo_y_ve_sales_el_coo_no`, `test_mandos_apagados_con_su_cobertura_real` PASS | — |
| Zona: destinatario → tenant → `configuration_required`; nunca UTC ni la del equipo | Se quita el respaldo «zona más frecuente del equipo». Nuevo `company.operational_time_zone` (migración **0026**) en Company Profile | `test_t4_sin_zona_pide_configuracion`, `test_zona_operativa_de_la_compania_en_el_perfil` (422 si no es IANA) PASS | **Hallazgo:** no existía zona de tenant. En la base local, Liber (CEO) y el superadmin no tienen zona propia: **sin fijar la zona de la compañía, sus T3/T4 quedan en `configuration_required`** |

## Hallazgo incidental (CONFIRMED, corregido)
**El formulario de Company Profile no se podía guardar** (422). Enviaba `domain` y `subdomain`, que el servidor rechaza a propósito (D5). El formulario deja de enviarlos y el control del servidor no cambia (`test_el_perfil_sigue_sin_aceptar_dominio_ni_subdominio`).

## Migración
`0026_company_time_zone`: añade una columna nullable y no rellena ningún valor. Up → down → up OK en local · 1 head.

## Comandos
- `uv run pytest` del lote de correos, permisos y superficie: **185 passed**, exit 0.
- `npm run check`: exit 0.

## Pendiente
- **Decisión de CER:** qué zona fijar en Company Profile para `cerroute`.
