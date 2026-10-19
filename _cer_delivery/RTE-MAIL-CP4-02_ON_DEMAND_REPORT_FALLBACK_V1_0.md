# RTE-MAIL-CP4-02 — Reportes a demanda y fallback manual de envio

**Producto:** CER Route  
**Modulo responsable:** CER Route Configuration > Activity Emails (interfaz y servicios de reportes existentes)  
**Version:** 1.0 | **Fecha:** 2026-10-19  
**Tipo:** instruccion de desarrollo para programador/agente  
**Dependencia coordinada:** `RTE-MAIL-CP4-01_DIGITALOCEAN_CRON_SCHEDULING_V1_0.md`  
**Decision de entrega:** autorizar boton, preview y envio controlado; sin habilitar suscripciones masivas o revelar notas reales hasta GO.

## 1. Context y baseline comprobable

De acuerdo con `RTE-MAIL-UNIFIED-01_V1_2_C_CP3_REPORT.md` (16-10-2026), existen en el desarrollo las cuatro plantillas y sus pruebas T1-T4; T0 prueba solo la integracion, y el cron automatizado NO estaba implementado. T1-T4 utilizan el endpoint `POST /api/activity-emails/templates/{tipo}/test-send` con **datos ficticios**. El test **nunca** debe reutilizarse para simular envio a usuarios reales: aqui se necesita una accion de negocio independiente, auditada y bajo permisos. El despliegue y la entrega real siguen sin validacion completa segun ese reporte.

Otras referencias de producto: `RTE-MAIL-UNIFIED-01_TEST_SEND_AND_STRATEGIC_REPORTS_V1_1.md`, `RTE-MAIL-UNIFIED-01_CP1_REPORT.md` y `RTE-MAIL-TEST-01_EXISTING_MAIL_VALIDATION_REPORT.md`.

**Necesidad confirmada:** si no funciona el cron o un directivo necesita un reporte inmediato, un usuario autorizado debe poder **generar/verificar** un reporte usando las plantillas aprobadas y, en una segunda accion explicitamente confirmada, **enviarlo a los destinatarios permitidos**. Debe funcionar incluso si no hay job de DigitalOcean ejecutandose, siempre que API/BD y proveedor esten disponibles.

## 2. Objective

Implementar en la seccion **Activity Emails existente**, sin nuevo menu independiente ni duplicar servicios de correo, una experiencia segura:

`Seleccionar tipo y periodo -> Generar reporte -> Vista previa REAL y control de elegibilidad -> Confirmar destinatario autorizado -> Enviar ahora -> Ver estado y auditoria`.

**Dos clases de reporte, cuatro plantillas:**

| Clase | Tipo | Sujeto del reporte | Contenido |
|---|---|---|---|
| Motivacional | `MIDDAY_MOTIVATION` | Un usuario habilitado | Mensaje personal + actividades hasta mediodia (sin notas ni rutas) |
| Motivacional | `END_OF_DAY_RECOGNITION` | Un usuario habilitado | Mensaje personal + dia + acumulado de semana, sin notas |
| Estrategico | `STRATEGIC_MIDDAY_REPORT` | Un mando autorizado | Cada descendiente autorizado: Breakdown/Details hasta mediodia; sin Team Weekly Summary |
| Estrategico | `STRATEGIC_END_OF_DAY_REPORT` | Un mando autorizado | Dia y detalles + semana individual para cada descendiente + **un Team Weekly Summary al final** |

T0 `Send Test Email` de Platform **no forma parte del reporte a demanda**. T1-T4 `Send test` con datos ficticios permanecen sin cambios.

## 3. Scope

1. Agregar la accion **Generate report / Generar reporte** y opcion controlada **Send now / Enviar ahora**, para los cuatro tipos en la misma pagina/area de Activity Emails existente.
2. Reutilizar las plantillas guardadas, el renderizador real, agregaciones, alcance jerarquico y politica de notas existentes. No generar textos paralelos ni recalcular categorias de otra manera.
3. Permitir seleccion restringida de destinatario, fecha operativa y tipo; previas dinamicas con datos **reales autorizados** y una indicacion visible del momento/corte utilizado; estados de dato parcial/cerrado.
4. Brindar un fallback **independiente de la ejecucion del cron**: si el envio programado vencio pero no ocurrio, el autorizado lo puede reponer manualmente; mismo ledger/idempotencia de CP4-01.
5. Exponer historial minimo de estados de envio, explicacion sin PII de fallos, identidad del operador, y diferenciacion `accepted_by_provider` vs `delivered`.
6. Pruebas RBAC, tenant/scope, temporales, fallos y concurrencia; UX web y responsive/movil administrativa donde corresponda.

**Out of scope:** descargar archivos de reportes, exportar datos completos de actividad, envio masivo indiscriminado, libre direccion de correo para un envio real de negocio, enviar a copias ocultas, cambiar `End Work` o GPS, activar programacion sin CP4-01, introducir un cron alternativo, reclasificar notas confidenciales automaticamente.

## 4. Placement and UX — cambio quirurgico

Reutilizar `CER Route Configuration > Activity Emails`, con grupos/controles actuales para **Motivational** y **Strategic**. No crear seccion adicional `Mail` ni mover integraciones de proveedor.

En la configuracion de cada plantilla ofrecer:
- `Preview sample` / `Send test`: **lo existente**, con datos ficticios y limitacion vigente; no confundir con envio real.
- `Generate report`: abre formulario compacto: **tipo de reporte** (preseleccionado), **destinatario habilitado/usuario o mando autorizado**, **dia operativo**, **momento de corte**, y **motivo** cuando se requiera envio extraordinario. Prever filtros/busqueda para tenant con muchos usuarios sin revelar identidades fuera de scope.
- Mostrar preview con persona(s) cubiertas, zona horaria del reporte, fecha y corte, etiqueta `Parcial` o `Cerrado` segun evidencias, cantidad de actividad registrada y cualquier campo retenido por confidencialidad. No presentar numeros inventados ni atribuir inactividad por ausencia de registro.
- Accion `Send now` deshabilitada cuando no hay consentimiento/configuracion o permiso, faltan requisitos de tiempo, proveedor no esta listo o el registro indica ya enviado. Antes de ejecutar, modal de confirmacion que identifica **quien recibe, que tipo, que ventana, si es parcial, y posible solapamiento con envio programado**.
- Historial cercano por destinatario/tipo/dia: `pendiente`, `aceptado por proveedor`, `sin envio`, `error`, `resultado incierto` con `requested_by` e instante. No mostrar secret keys, notas a personas no autorizadas, ni errores tecnicos crudos.
- No usar botones inertes ni depender de que un usuario abra una pestana para ejecutarse. Responsive sin replicar en My Route ni dar acceso a Supervisor/Execute sin permiso explicito.

## 5. Roles, permisos, destinatarios y scope

- **Platform administrator:** puede ejecutar pruebas T0 segun permisos actuales; su rol por si solo no autoriza difundir informacion operativa real entre tenants. Para enviar un reporte real, usar grants y scope de reporte correspondientes (evitar el atajo de enviar arbitrariamente porque es superadmin).
- **Tenant admin / administradores autorizados:** pueden gestionar plantillas/preferencias segun `route.activityemails.manage` existente; distinguir capacidad de configurar de capacidad de **generar/ver datos reales** y de **enviar** (nuevas capacidades granulares si la plataforma de permisos necesita esa separacion). No ampliar el permiso existente en silencio.
- **Mando receptor con derecho jerarquico:** puede generar/recibir solo su propio reporte estrategico sobre descendientes autorizados, segun permisos y data access grants en el momento de lectura y envio; no seleccionar otro mando o un email externo por medio de identificadores manipulados.
- **Usuario de correo motivacional:** por defecto no recibe una opcion de administracion de envios ni accede a reportes ajenos; cualquier autoservicio posterior queda fuera de este checkpoint.
- Los destinatarios reales deben proceder del **perfil/suscripcion autorizada** y ser verificables conforme la politica vigente. Campo libre para email **solo** en T0 controlado para plataforma y bajo su politica de pruebas; nunca en `Send now` real.
- Revocacion de rol, cambio de jerarquia, salida de empleado o cambio de tenant invalida preview obsoleto y exige reevaluar antes del envio (no reutilizar un token de vista previa como permiso).
- Strategic: directos + indirectos **autorizados**, CEO incluye Sales cuando Sales depende del CEO, COO no incluye Sales por defecto, sin duplicacion. Excluir trabajo propio del mando salvo decision de producto diferente.

## 6. Datos y ventanas temporales — comportamiento obligatorio

### 6.1 Midday solicitado manualmente

- Si el usuario selecciona `Midday` y la hora local del dia elegido ya supero las 12:00, generar **corte fijo a las 12:00** del dia indicado, aunque se pulse el boton mas tarde. Indicar `Corte: 12:00 p.m.` y `Generado: [hora real]` para no confundir.
- Si es antes de las 12:00, permitir **preview parcial "hasta ahora"** si es necesario, etiquetado `Vista parcial, no reporte de mediodia final`; `Send now` con tipo Midday oficial no debe emitirse anticipadamente sin una excepcion de producto explicita. Si fecha pasada, asegurar que `session_date` y el offset correcto determinan la ventana y que no cambian datos historicos.
- Motivacional: si no se completa al menos una actividad elegible antes de mediodia, mostrar `Sin actividades elegibles para este envio` y no mandar email; no enviar motivacion sin actividad por esta funcionalidad, segun el requisito previo reportado.
- Estrategico: computar cada descendiente segun permiso; no atribuir incumplimiento a quien no registra actividades. Nunca agregar Team Weekly Summary a Midday.

### 6.2 End of day solicitado manualmente

- Motivacional: correo final **solo para una jornada validamente cerrada** (con los criterios aprobados de `End Work`); si la jornada se reanudo o sigue abierta, permitir preview marcado `Parcial` pero no presentar `jornada finalizada` ni ejecutar envio como cierre definitivo.
- Estrategico: un reporte final tiene que estar respaldado por cierre fiable de equipo o cutoff maximo aprobado. Cuando no haya evidencia de completitud, un preview `Parcial hasta HH:MM` es valido, pero **no enviarlo como si fuera un cierre total**. La opcion de envio extraordinario de un corte parcial requerira autorizacion adicional y asunto visible `Reporte parcial`, si el PO aprueba esa modalidad posteriormente; mientras tanto no enviar.
- Semana individual y Team Weekly Summary se calculan de forma identica al reporte automatico; acumulan hasta el cutoff real de la semana del periodo, por categoria, sin contar dos veces personas ni eventos. No incluir una semana completa de notas: solo detalles del dia.
- En jornadas que cruzan medianoche, usar dia operativo local de inicio y timestamps aware, no cerrar automaticamente ni recalcular historicos a UTC.

### 6.3 Confidencialidad de notas

Mantener requisito funcional de Activity Details y notas, pero **ninguna nota libre real sale a email antes de DP-NOTES**. Para preview de informacion real, aplicar permisos de lectura por campo y redaccion en backend; para envio sin politica aprobada, reemplazar por `Detalle no incluido en el correo`. Ningun nuevo preview debe ser un bypass de permisos que los reportes normales aplican.

### 6.4 Decisiones de producto aun pendientes

- `DP-WEEK`: lunes recomendado; no inventar que esta aprobado.
- `DP-TIMEZONE`: fuente autoritativa de timezone de usuario/mando, zonas distintas y DST.
- `DP-CUTOFF` y `DP-TEAM`: hora maxima de estrategico final y evidencia de cierre completo.
- `DP-NOTES`: campos admitidos y tratamiento por rol/jurisdiccion.
- `DP-RECOVERY`: ventana maxima de backfill de correos omitidos, sin mandar correos viejos de golpe.

**Gating:** previews con datos ficticios pueden desarrollarse y probarse ya; los envios reales se habilitan por tipo solo cuando su politica temporal/de privacidad es verificable. Mostrar motivo de `Send now` deshabilitado en lugar de simular exito.

## 7. Reutilizacion del dispatcher e idempotencia — contrato compartido con CP4-01

Ambas instrucciones deben producir **un solo servicio de delivery** y una sola tabla/unique key para el mismo destinatario, tipo, tenant, fecha operativa y corte/periodo. Las llamadas de UI y los cron/scheduler usan el mismo metodo de claim transaccional y reglas de autorizacion. No reutilizar `mail_test_send` (tabla de pruebas T0-T4) para correspondencia real.

- **Generate preview** no escribe en el ledger productivo ni consume cuota de envios reales; nunca causa email.
- **Send now — recuperacion de un pendiente vencido/no enviado:** reclama la misma llave del automatico; si luego corre cron, este ve `ACCEPTED_BY_PROVIDER`/reserva y **no duplica**. Si cron ya reservo el mensaje, la UI muestra que esta en curso.
- **Ya aceptado por proveedor:** no permitir por defecto volver a enviarlo al pulsar. Ofrecer estado e instante de aceptacion; no afirmar que fue entregado.
- **Fallo definitivamente no enviado:** accion `Reintentar` sobre el mismo registro (no segunda entrega), bajo presupuesto/backoff y limite, con justificacion cuando corresponda.
- **Resultado incierto (timeout tras transferencia):** no reenviar a ciegas; mostrar `Resultado de entrega incierto; requiere conciliacion`.
- **Reenvio intencional de un mensaje ya aceptado:** fuera del flujo normal; solo si existe permiso privilegiado, razon obligatoria y registro de un `resend_revision` independiente, con aprobacion del PO para esa experiencia. No implementar redireccion libre ni listas CC/BCC.
- **Enviar antes del vencimiento:** por defecto solo preview. Una excepcion anticipada debe diferenciarse de la entrega programada, con reglas de supresion/duplicidad aprobadas; no inventar comportamiento. El uso principal de este boton es **recuperar envios debidos no ejecutados**.
- **Provider unavailable:** Generar y preview funcionan; `Send now` informa fallo de proveedor y guarda estado seguro, no promete que esta enviado; se puede volver a intentar cuando se restablezca.

Estados recomendados identicos a CP4-01: `PENDING`, `CLAIMED`, `ACCEPTED_BY_PROVIDER`, `RETRYABLE_FAILURE`, `PERMANENT_FAILURE`, `SKIPPED`, `UNKNOWN_OUTCOME`.

## 8. Contratos API / UI — elegir rutas conforme convenciones reales

Conservar y **no alterar semantica** de `POST /api/activity-emails/templates/{tipo}/test-send`. Implementar contratos autenticados separados, conceptualmente:

```text
POST /api/activity-emails/reports/preview
  { report_type, recipient_user_id, operational_date, as_of? }
  -> { report_type, recipient, cutoff, timezone, provisional,
       eligible, ineligible_reason?, sanitized_preview, authorized_coverage_count }

POST /api/activity-emails/reports/send
  { report_type, recipient_user_id, operational_date, requested_reason?, confirmation_token? }
  -> { delivery_id, status, cutoff, destination_masked, accepted_by_provider:false }

GET /api/activity-emails/reports/deliveries?recipient=...&date=...
  -> historial autorizado (sin cuerpos/notas/secretos)
```

**Son contratos ilustrativos, no rutas previamente implementadas.** Alinear con arquitectura/API y validar de nuevo servidor-side `recipient_user_id`, tenant, scope, fecha, correspondencia preview/send, estado de envio y confirmacion. Rechazar campos extra que intenten inyectar destinatario email, HTML, scope o datos de actividad. Si hay render HTML, sanitizar y defenderse de notas no confiables.

No permitir crear ID de destinatario arbitrario en el frontend para ganar derechos. Respuestas claras ante 401/403/409/422/429/502 y provider not configured. La UI no debe mostrar `delivered` sin evidencia independiente: mostrar `Aceptado por proveedor` y señalar que no garantiza recepcion.

## 9. Audit, privacy and regression

Trazar actor, tenant, tipo, ID del destinatario permitido, fecha operativa, cutoff, request_id/correlation_id, motivo de recuperacion, outcome y timestamps, sin guardar cuerpo de email, notas completas, secretos ni excepciones proveedor. Proteger tambien la previa real (PII), nunca servir desde cache publico ni permitir enlaces compartibles no autenticados. Configuraciones/activaciones siguen OFF por defecto hasta GO, y no se alteran por pulsar preview. Rate limiting para envios reales y prevencion de doble clic/concurrencia. Respetar la limitacion vigente de T0-T4 de 5 tests/15 min, sin contarlos como correo productivo.

## 10. Acceptance criteria — controles funcionales

| ID | Criterio verificable |
|---|---|
| OD-01 | Opciones Generate report y Send now se integran sin nueva navegacion y con T0-T4 intactos |
| OD-02 | Cada uno de los cuatro tipos muestra preview autorizado con **plantilla guardada**, ventana y destinatario real valido; no datos ficticios en produccion sin etiqueta |
| OD-03 | Motivacional mantiene minima exposicion: sin notas, rutas, coordenadas, clientes, millas ni combustible en contenido |
| OD-04 | Midday respeta corte 12:00 local; antes de las 12:00 solo preview parcial, sin afirmacion de reporte final |
| OD-05 | Motivacional cierre exige End Work valido y actividades; si fue reabierto no se envia como cerrado |
| OD-06 | Strategic CEO/COO/reemplazos y grants, scope directo/indirecto, notas protegidas y sin datos cross-tenant |
| OD-07 | Strategic final muestra cada persona (dia y semana) y **un** Team Weekly Summary al final; concilian cifras sin doble conteo |
| OD-08 | Accion de envio recupera un slot vencido omitido; cron posterior no repite mensaje. Preview no consume slot |
| OD-09 | Error, ausencia de proveedor, reintento, accepted/unknown outcome se muestran honestamente; reenviar aceptados esta bloqueado |
| OD-10 | Permisos diferenciados `manage`, `view_real_report` y `send` (o equivalentes reales) validos en backend y UI, sin privilegios nuevos tacitos |
| OD-11 | Historico/auditoria sin contenido sensible ni secretos; doble clic, 2 replicas, carrera cron/manual, revocacion entre preview y send probadas |
| OD-12 | Tests responsive, regresion de las cuatro plantillas y T0, capturas de flujo completo, migraciones y reporte de evidencia |

## 11. Tests Required

- Unit: periodos de corte, no actividad motivacional, notas autorizadas/redactadas, semana individual/team total, DST, overnight, falta de zona, estados incompletos.
- Integration DB/API: 401/403 por actor/tenant/grant; 422 campos extra; 409 ya enviado/claimed; fallo proveedor seguro; reintento de fallos; 2 pulsaciones simultaneas; cron y manual simultaneos; historial aislado.
- E2E desktop/movil administrativo: generar las cuatro previas, error de permisos, confirmacion y `Send now` controlado contra backend simulado, estados y muestra de resultados.
- Stage: backend real con test mailbox autorizado; envio manual **real** solo a destinatario CER autorizado con datos reales redaccion segura y consentimiento apropiado; verificar recepcion separadamente del `accepted_by_provider`. No usar contactos reales operativos hasta GO.

## 12. Checkpoints y entregables

- **CP4-02A — UI + Preview:** controles y cuatro previas reales con RBAC/tenancy. Todas las acciones productivas de envio deshabilitadas hasta contrato comun + gates; demos T0-T4 siguen operando.
- **CP4-02B — Envio manual seguro:** API/servicio compartido, consent/eligibilidad, idempotencia, historial, confirmacion, errores y reintentos.
- **CP4-02C — Pruebas integradas:** carrera manual/cron, despliegue de pruebas, screenshots, regresiones, pruebas reales controladas y runbook operativo.

Entregar `RTE-MAIL-CP4-02_REPORT.md` con Expected -> Implemented -> Evidence -> Gap -> Impact, tablas/rutas nuevas, permisos, migraciones y tests, estados `Completed/Partial/Blocked`, decisiones PO pendientes, capturas y pasos para reproducir. **No declarar DONE si falta evidencia de recepcion real o hay bloqueo DP relevante.**

**Do Not Change:** copia aprobada de las cuatro plantillas, seccion Activity Emails, flujo `End Work` / `Keep working`, pruebas T0-T4 y su presupuesto, logica de jerarquia, metricas oficiales y aislamiento de tenant. No crear otro motor de calculo de correo ni otra tabla de deliverability paralela.
