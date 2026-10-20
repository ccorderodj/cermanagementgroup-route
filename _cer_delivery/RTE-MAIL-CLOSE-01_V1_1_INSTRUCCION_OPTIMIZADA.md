# RTE-MAIL-CLOSE-01 — Activación automática + cierre de brechas (V1.1)

**CER Route | Instrucción ejecutable, compacta | 2026-10-20**  
**Prioridad:** P0. **Objetivo:** dejar los cuatro correos **automáticos, precisos y observables**; mejorar exclusivamente el reporte estratégico y certificar ejecución real.  
**Autoridad:** sustituye en V1.0 las reglas de horario de T4 y población reportada. El resto del alcance de V1.0 se mantiene solo cuando no contradiga esta instrucción.

## Para el agente (ejecución eficiente)

**Implementa, no vuelvas a diseñar.** Lee solo los componentes directamente afectados y los reportes ya entregados; usa búsquedas dirigidas, `git diff` y tests focalizados. No repitas inventarios, explicaciones de arquitectura ni preguntas ya resueltas. Reutiliza lo existente. Decide detalles técnicos menores, pero **no inventes reglas de negocio**. Ejecuta CP1 → CP2 → CP3 de forma continua; detente solo por credenciales/acceso o decisiones imprescindibles para habilitar envíos reales. Reporta brechas con evidencia, no con suposiciones.

**Baseline a confirmar contra código y despliegue:** cuatro plantillas T1–T4; `Activity Emails`; `real_reports.py` y `delivery.py`; scheduler interno con liderazgo PostgreSQL; ledger `activity_email_delivery` (0024); `Resend`/auditoría (0025, MR !111); App Spec/cron DigitalOcean; Microsoft 365. No asumir que un MR fusionado implica deploy ni que `Verify/accepted_by_provider` prueba recepción.

## Contrato funcional aprobado (no reinterpretar)

| Tipo | Destinatario | Disparador obligatorio | Contenido |
|---|---|---|---|
| **T1 Midday Motivation** | Execute / usuario habilitado | **12:00 PM** de su zona configurada | Plantilla motivacional vigente, sin cambios. Mantener reglas actuales de elegibilidad. |
| **T2 End of Day Recognition** | Execute / usuario habilitado | **20 minutos después de End Work** (NO 10) | Plantilla vigente, sin cambios; reabrir jornada antes del envío aplaza el vencimiento. |
| **T3 Strategic Midday** | CEO/COO/mando habilitado | **12:00 PM** de la zona del destinatario | Resumen por persona **al corte de mediodía**, sin acumulado semanal. |
| **T4 Strategic End-of-Day** | CEO/COO/mando habilitado | **7:00 PM (19:00)** de la zona del destinatario | Resumen diario, WorkSession individual, semana por persona y **un único Team Weekly Summary al final**. |

- **T4 es horario fijo**: **nunca anticipar** por cierre del último trabajador y **no retrasar** por jornadas abiertas. Producir snapshot de las 19:00 identificando pendientes. Un envío programado por destinatario/tipo/día operativo. Mantener Send Now/Resend con controles separados; no convertirlos en disparadores adicionales.
- T1/T3 comparten la hora **local** de las 12:00, no una hora UTC común. Resolver IANA del destinatario/perfil o tenant **desde configuración vigente**, con fallback explícito a zona del tenant; si no existe una zona inequívoca, registrar `configuration_required` y solicitarla, **nunca asumir UTC ni la zona mayoritaria del equipo**.
- CEO está representado actualmente por **admin/superadmin**: **decisión cerrada**, no crear rol CEO. Acceso solo al **tenant explícito**; CEO incluye Sales conforme a jerarquía vigente, COO **no** incluye Sales. RBAC y scope se validan en backend.
- No modificar horarios de WorkSession, estados de Activity, reglas de jornada a través de medianoche, millas/odómetro ni cálculos oficiales. Semana: **reutilizar período de lunes a corte** implementado, sin redefinirlo.

## Brechas que debes cerrar

**A. Población y estados en T3/T4 (P0)**

- Construir el listado desde **usuarios activos elegibles del scope jerárquico**, no desde quienes tienen actividades. Incluir persona aunque **no tenga Start Work ni actividades**; no duplicar colaboradores por niveles jerárquicos.
- Por persona: `Start Work` real, `End Work` real si ocurrió, estado **Sin registro de inicio al corte / En curso / Finalizada**, duración de **jornada registrada** cuando sea calculable, conteos de Activity. No calificar **Ausente** a quien no inició: no hay evidencia suficiente.
- Usar exclusivamente **WorkSession** para entrada/salida y duración de jornada; distinguirla de tiempo en actividades y de horas pagadas. Si hay varias sesiones, utilizar el contrato de sesiones real, no deducir la jornada de primera/última Activity. Entrada posterior a las 12:00 = **sin registro de inicio al corte** en T3; si sigue abierta a las 19:00 = **En curso** en T4.
- T3/T4 deben reflejar usuarios sin actividad dentro de su roster; evitar que `no_team_activity` suprima el reporte estratégico cuando hay destinatario habilitado y personas elegibles. Si el roster autorizado está vacío, declarar omisión con motivo.
- Executive Snapshot: total del roster, sin inicio, en curso, finalizados; eventos y millas válidas del corte. T4: continuar con breakdown/detalles de cada persona, resumen semanal individual y **Team Weekly Summary** único. Plantillas T3/T4 siguen editables; nuevos campos con variables controladas. **No enviar notas libres reales** hasta política aprobada.

**B. Integridad del corte de mediodía (P0)**

- Una actividad **11:30–13:26** no debe figurar a las 12:00 como `Finalizada`, ni computar duración/eventos/millas futuros como realizados al corte. Aplicar temporalidad real a T1 y T3 sin alterar registros originales ni presentar datos posteriores registrados tarde como conocidos al corte.
- Resolver agregaciones en segundos y redondear solo en presentación; comprobar suma persona/categoría/equipo con el ejemplo reportado del 19/10 (minutos inconsistentes). No inventar costo estimado cuando no existe.

**C. Scheduler y ejecución real (P0)**

- Auditar **App Spec real de DigitalOcean**: contrastar los **3 jobs anunciados** con el reconciliador `*/15` anterior; adoptar la menor configuración suficiente, no duplicar tareas ni reemplazar App Spec actual con una propuesta vieja.
- Scheduler interno (precisión hasta minuto) + job(s) DigitalOcean de recuperación deben compartir servicio, reglas de elegibilidad, **ledger y clave única**. No depender de un cron de 15 minutos para prometer End Work +20 exactos; tolerancia de un ciclo del scheduler y registrar retrasos reales.
- Verificar jobs efectivamente desplegados, comandos, horario/zona, migraciones, logs, reinicios, idempotencia, reintentos y kill switch. **Activar** T1/T2/T3/T4 por fases solo tras validación controlada; dejar evidencia de **dos ejecuciones reales** de job y de un ciclo de mediodía + cierre (incluido T2 por End Work). Si no hay acceso a DO, entregar cambio aplicable y procedimiento exacto, estado **BLOCKED**, no declarar automatización operativa.
- Reportar cuándo un corte de las 19:00 se perdió por caída y fue recuperado; mantener ventana existente de recuperación salvo aprobación de cambio. Nunca mandar correos antiguos silenciosamente ni duplicar manual/cron/reenvío.

**D. Historial y estado visibles (P1, dentro del mismo desarrollo)**

- En la **configuración actual de Activity Emails**, exponer/terminar **Delivery History** usando `activity_email_delivery`, reenvíos, pruebas/auditoría cuando aplique: fecha, tipo, destinatario autorizado, zona/corte, disparador (`scheduler`, `reconcile`, `manual`, `resend`), fecha de intento, estado, motivo sanitizado y próximo reintento. Filtros por período, tipo, destinatario y scope. Sin cuerpos, notas, secretos ni errores crudos.
- Reemplazar «automatización pendiente» fijo por estado **leído del backend**: provider Verify, enabled/dry-run, tipos activos, última ejecución observada/job no verificado. **Accepted by provider ≠ Delivered**.
- Conservar `Generate report`, `Send now`, `Resend`, permiso separado `route.activityemails.resend`, cuotas, historial e idempotencia. No habilitar reenvío por defecto ni cambiar T1/T2.

## Pruebas obligatorias (solo evidencia concluyente)

| Test | Evidencia mínima |
|---|---|
| T1/T3 12:00 | Usuario con actividad que termina 13:26, sin datos posteriores al corte; varias zonas IANA y DST. |
| T2 +20 | +19 no envía, +20/-tolerancia sí, reapertura aplaza, dos sesiones, medianoche. |
| T4 19:00 | 18:59 no envía aun con equipo cerrado; 19:00 envía aunque queden jornadas abiertas; entrada/salida/estados correctos; sin-inicio incluido. |
| Scope | CEO admin/superadmin en tenant explícito incluye Sales; COO no ve Sales; cross-tenant 403/404. |
| Datos | Totales exactos y semana individual + Team Weekly Summary único; no inferir `Absent`, costo, notas ni duración pagada. |
| Entrega | Cron + scheduler + Send Now sin duplicados; fallo/recovery; ledger e historial UI coinciden; `Resend` preservado. |
| Producción | Dry-run controlado, pruebas reales a buzones autorizados, recepción comprobada de T1–T4, captura de job/logs/Delivery History. |

Mantener tests preexistentes documentados separados de regresiones nuevas; ejecutar tests relacionados + build + regresión razonable. No afirmar suite completa PASS si hay fallos.

## Checkpoints / entregables (sin detenerse entre CP1 y CP2)

1. **CP1 — Corte, roster y horarios:** código + tests sobre estados al corte, T3/T4 sin-inicio, T4 19:00, T2 +20; sin tocar texto motivacional.
2. **CP2 — UX estratégico e historial:** WorkSession real y executive snapshot en T3/T4, Delivery History y estado operativo; screenshots escritorio/móvil, permisos.
3. **CP3 — DigitalOcean / GO operativo controlado:** conciliar y aplicar App Spec real, migraciones, dry-run, habilitación por tipos/destinatarios, validación recepción y rollback. Implementar todo lo accesible; clasificar como **Blocked** cualquier acción externa no ejecutable, con pasos precisos.

**Entregar un MD por checkpoint**, máximo 1–2 páginas cada uno, con `Expected → Implemented → Evidence → Gap/Impact`, commits/MR, migraciones, comandos+resultados de tests, evidencia real de deploy/recepción o bloqueo, y pendientes genuinos. Evitar narrativas extensas, estimaciones de líneas y recuentos repetidos. **Done solo con evidencia de ejecución automática y contenido correcto.**

## Do Not Change

No nueva área Mail; no rediseño V0.7; no cambio al correo motivacional de Execute; no nuevos roles CEO; no acceso cross-tenant; no notas reales sin autorización; no cambiar WorkSession/End Work ni millas oficiales; no enviar a todos sin fase piloto; no exponer PII en logs; no declarar entregado solo porque Microsoft aceptó.
