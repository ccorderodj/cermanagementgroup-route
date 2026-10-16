# RTE-NOT-01: Activity Emails, plantillas y destinatarios

**Reporte técnico 001** · 15 de octubre de 2026
**Instrucción:** `_cer_delivery/RTE-NOT-01_ACTIVITY_EMAIL_TEMPLATES_RECIPIENTS_V1_0.md`
**Status: COMPLETED WITH PENDING VALIDATION.** Implementado y validado en local, contra la base de tests. Pendiente: certificación del PO, despliegue y decisiones DP-02/DP-03.

> **El envío de correos NO está implementado en este checkpoint.** Guardar, activar o previsualizar sólo almacena configuración. No hay programador, ni agregación, ni envío. Eso es RTE-NOT-02/03 y no está autorizado.

## 1. Alcance por checkpoint

| Checkpoint | Estado | Evidencia |
|---|---|---|
| CP-01: auditoría de reutilización y contratos | **Completed** | Sección 2 |
| CP-02: plantillas (persistencia, texto aprobado, editor, validación, vista previa, restaurar, auditoría) | **Completed** | Tests de las secciones 6.1-6.3, capturas |
| CP-03: destinatarios (búsqueda, dos interruptores, alcance, estados negativos) | **Completed** | Tests de las secciones 6.2-6.3, capturas |
| CP-04: validación y entrega | **Completed** | Este documento, sección 6.4 |

## 2. CP-01: qué había y qué se reutilizó

| Necesidad | Lo que existe | Decisión |
|---|---|---|
| Settings > Notifications | **No existe.** El menú lateral tiene «CER Route» (trabajo) y «CER Route Configuration» (configuración) | **DP-01:** «CER Route Configuration › Activity Emails» (`/admin/route/activity-emails`). Crear un «Settings» solo para esto sería una navegación paralela, que §3.1 prohíbe |
| Pestañas, formularios, toasts, confirmación | `Tabs`, `Input`, `Textarea`, `Card`, `useToast`, `ConfirmDestructiveDialog` | Reutilizados |
| Directorio de usuarios y alcance | `usermanagement` + `organization.delegation` (`delegacion`, `gestionables`, `exigir_objetivo`) | Reutilizados: el mismo alcance jerárquico que la administración de usuarios |
| Correo verificado | **No existe** un concepto de «correo verificado» en la cuenta | Se usa el correo de la cuenta con validación sintáctica (`email_validator`, sin DNS). Brecha documentada en la sección 8 |
| Permisos | Catálogo único `app/core/rbac/catalog.py`; no hay capacidad de notificaciones | Nueva capacidad acotada `route.activityemails.manage`, **a demanda** (sección 4) |
| Auditoría | `app/core/audit` `record_event` → `audit_event` (append-only) | Reutilizada; sin segundo subsistema |
| Concurrencia | `VersionedMixin` + `ensure_version` (409) | Reutilizados |
| Enum de negocio | `BusinessEnum` + CHECK derivado | Reutilizado para el tipo de plantilla |
| Correo saliente | `app/core/email/backends.py` (SMTP, M365, consola) | **No se usa** en este checkpoint. Es el que debe usar RTE-NOT-02/03 |
| Programación | `app/core/platform/scheduler.py` (`register`, candado consultivo) | **No se usa** en este checkpoint. Recomendado para RTE-NOT-02/03 |

## 3. Modelo de datos y migración

**Migración `0021_activity_email_settings`** (revisa `0020_org_replaces_user`). Un solo head.

| Tabla | Contenido | Restricciones |
|---|---|---|
| `activity_email_template` | `company_id`, `template_type`, `subject`, `body`, `version`, `updated_by_user_id`, timestamps | Única `(company_id, template_type)`; CHECK de tipo (`midday_motivation`, `end_of_day_recognition`); CHECK asunto no vacío, ≤200, **sin saltos de línea**; CHECK cuerpo no vacío, ≤5000 |
| `activity_email_preference` | `company_id`, `user_id`, `midday_enabled`, `end_of_day_enabled`, `version`, `updated_by_user_id`, timestamps | Única `(company_id, user_id)`; **FK compuesta `(user_id, company_id)` → `user_company`**: la base rechaza a alguien de otra compañía; los dos booleanos con `DEFAULT false` |

**La migración no escribe ninguna fila (BR-04).**
- Nadie queda suscrito.
- Ninguna compañía recibe plantillas sembradas: el texto aprobado vive en `activityemails/content.py` y se muestra mientras la compañía no lo personalice. La fila nace con el primer guardado o restauración.
- **Desviación consciente.** §11 AC-02 habla de «initialized». Se cumple por API, y una compañía nueva tiene las dos plantillas desde el primer momento sin aprovisionamiento ni un paso nuevo en `converge`.

**Bajada (downgrade):** borra las dos tablas. Los cambios siguen en `audit_event`.

## 4. Permiso

- **`route.activityemails.manage`:** una sola capacidad para leer y cambiar, porque leer esta configuración sin poder cambiarla no sirve a nadie. La exigen las 6 APIs y la página.
- **A demanda, en `CAPACIDADES_A_DEMANDA`:** **ninguna plantilla de rol la concede**, tampoco owner ni admin, así que no se amplía ningún rol (§8).
  - El Superadmin entra sin concesión.
  - Cada tenant la asigna en Roles & Permissions. El Superadmin lo aplica al momento (MR !99).
- **Un CEO, COO o RM con la capacidad solo ve y cambia a su rama:** misma delegación que Users; fuera de ella, 404.

## 5. API (`/api/activity-emails`, privada; no está en `/api/v1` ni en la superficie pública)

| Método y ruta | Qué hace | Errores |
|---|---|---|
| `GET /templates` | Las dos plantillas: texto efectivo, `is_default`, `version` (0 sin fila), editor y fecha, variables y obligatorias | 401, 403 |
| `PUT /templates/{tipo}` | Guarda **una** plantilla `{subject, body, version}`; audita `update` | 404 tipo desconocido, 409 versión vieja, 422 por campo (`loc: [body, subject \| body]`) |
| `POST /templates/{tipo}/restore-default` | Texto aprobado en **esa** plantilla `{version}`; audita `restore_default` | 404, 409 |
| `POST /templates/{tipo}/preview` | Borrador con datos **ficticios**, `is_sample: true`, «Ejemplo / Vista previa». No escribe ni envía | 404, 422 |
| `GET /recipients?q&page&page_size` | Personas cuyo rol concede `route.worksession.execute`, no borradas, dentro del alcance; con `eligible` e `ineligible_reason` (`inactive` / `invalid_email`) | 401, 403 |
| `PUT /recipients/{user_id}` | Uno o los dos interruptores `{midday_enabled?, end_of_day_enabled?, version}`; el que no viene no cambia; audita `update` con el diff | 400 sin cambios, 404 otro tenant o fuera de alcance, 409 activar a alguien no elegible o versión vieja, 422 campo extra (por ejemplo `email`) |

## 6. Validación

### 6.1 Reglas de contenido (`content.py`)
- **Variables permitidas:**
  - mediodía: `user_first_name` y `midday_activity_block`;
  - fin de jornada: `user_first_name`, `day_activity_block` y `week_activity_block`;
  - asunto: solo `user_first_name`.
- **Bloques obligatorios (BR-07):** mediodía, `{{midday_activity_block}}`; fin de jornada, `{{day_activity_block}}` y `{{week_activity_block}}`.
- **Se rechaza:**
  - una variable desconocida o de la otra plantilla;
  - sintaxis rota (`{{ user.name }}`, `{% %}`, llaves sueltas);
  - HTML y enlaces (`http(s)://`, `www.`, `javascript:`, `data:`);
  - un asunto multilínea, que sería inyección de cabeceras;
  - textos vacíos o demasiado largos.
- **Render:** sustitución literal de marcadores, sin motor de plantillas ni evaluación.
- **UTF-8 y emojis:** se conservan.

### 6.2 Tests ejecutados (local, PostgreSQL de tests)

| Lote | Comando | Resultado |
|---|---|---|
| Unitarios de contenido y catálogo | `uv run pytest tests/test_activity_email_content.py` | **29/29 PASS** |
| Integración RTE-NOT-01 | `uv run pytest tests/integration/test_activity_emails.py` | **22/22 PASS** (primera ejecución: 1 ERROR de montaje, corregido; ver sección 7) |
| Cableado, menú, catálogo, superficie pública, registro de converge | `uv run pytest tests/test_page_wiring.py tests/test_navigation_wiring.py tests/test_permission_catalog.py tests/test_public_surface.py tests/test_converge_registry.py` | **70/70 PASS** (primera ejecución: 1 FAIL, corregido; ver sección 7) |
| Regresión vecina: actividades, Activity, mapa, aprobación de permisos, My Activity, jerarquía, reincorporación, alineación RTE08, Superadmin | 9 ficheros | **221/221 PASS**, exit 0, 451 s |
| Navegador (Edge, build de producción) | `uv run pytest tests/e2e/test_activity_emails_browser.py -n 0` | **3/3 PASS** (primeras ejecuciones: 2 FAIL, corregidos; ver sección 7) |
| Migración | `alembic heads` | `0021_activity_email_settings (head)`, un solo head |
| Frontend | `npm run check` / `npm run build:prod` | exit 0 / exit 0 |
| Regresión completa (unitarios + integración) | `uv run pytest tests --ignore=tests/e2e` | **1.413 recogidos, 1 FAIL preexistente**, 1.034 s (sección 6.4) |
| E2E completos (las demás pantallas) | — | **NOT RUN**: el cambio de frontend se limita a una página nueva y a un ítem de menú |

### 6.3 Criterios de aceptación

| AC | Estado | Evidencia |
|---|---|---|
| AC-01 área con Templates y Recipients | VALIDATED | E2E llega por el menú; `escritorio-templates.png` |
| AC-02 texto aprobado inicial | VALIDATED | `test_nacen_con_el_texto_aprobado`, `test_los_textos_aprobados_son_validos_y_literales` |
| AC-03 persiste y por tenant | VALIDATED | `test_guardar_persiste_por_tenant_y_no_toca_la_otra`; E2E recarga |
| AC-04 vista previa ficticia, sin envío | VALIDATED | `test_vista_previa_ficticia_sin_escribir`; `escritorio-preview.png` |
| AC-05 variables inválidas y bloques | VALIDATED | 5 casos de integración + 18 unitarios; `escritorio-validacion.png` |
| AC-06 restaurar con confirmación, solo la elegida | VALIDATED | `test_restaurar_solo_la_elegida`; `escritorio-restaurar.png` |
| AC-07 alcance de tenant y jerarquía | VALIDATED | `test_un_mando_solo_ve_y_cambia_su_rama`, `test_otro_tenant_o_fuera_de_lista_es_404` |
| AC-08 interruptores independientes, apagados por defecto | VALIDATED | `test_interruptores_independientes_y_auditados`, `test_lista_quien_ejecuta…`, `test_la_base_rechaza…` |
| AC-09 sin correo válido o inactivo no se activa | VALIDATED | `test_sin_correo_valido_o_inactivo_no_se_activa`, `test_preferencia_de_un_activo_que_se_suspende…` |
| AC-10 auditoría y 403 en backend | VALIDATED | `test_sin_la_capacidad_todo_es_403` (6 endpoints × 5 roles), eventos en los tests |
| AC-11 móvil y accesibilidad básica | VALIDATED (básica) | `movil-*.png`, sin scroll horizontal a 390 px; interruptores `role="switch"` con nombre, errores `role="alert"`. **Sin auditoría formal WCAG** |
| AC-12 Start/End Work intactos, sin envío | VALIDATED | Diff: no toca jornada, actividades ni correo; regresión vecina 221/221 |
| AC-13 conflicto sin pérdida silenciosa | VALIDATED | `test_version_vieja_es_409_sin_perder_nada`, 409 en destinatarios y restaurar |
| AC-14 la interfaz dice «solo configuración» | VALIDATED | Banner «Configuración guardada. Envío automático pendiente de habilitación.» y aviso en Recipients |

### 6.4 Regresión completa
`uv run pytest tests --ignore=tests/e2e`: **1.413 tests recogidos, 1 FAIL**, exit 1, 1.034 s. Los otros 1.412 pasaron u omitieron; el desglose entre los dos no quedó capturado.

- **Único fallo: `test_provisioning_alignment::test_the_two_product_roles_hold_exactly_twelve_and_two_capabilities`.**
  - **Preexistente desde RTE09** (`CONFIRMED`): espera 12 capacidades para `route_admin` y hay 16.
  - No lo causa este cambio: la capacidad nueva es a demanda y no entra en ninguna plantilla.
- La carrera entre tests de migraciones del reporte anterior **no se repitió** en esta ejecución.

## 7. Hallazgos y fallos durante la ejecución (todos corregidos)

| Qué | Causa | Acción | Estado |
|---|---|---|---|
| 1 ERROR en `test_sin_sesion_es_401` | **CONFIRMED:** el test no pedía el fixture `seeded`, que es el que prepara la base del worker | Se añadió `seeded` | PASS |
| 1 FAIL en `test_every_page_template_is_covered_by_the_anchor_test` | **CONFIRMED:** la plantilla nueva no estaba en la lista de anclas (el test existe para obligar a esto) | Añadida | PASS |
| 2 FAIL en E2E: no encontraba `data-testid` | **CONFIRMED:** el build de producción elimina `data-testid` (`buildBabelLoader.ts:37`) | El test localiza por rol y nombre accesible; las tarjetas pasan a ser `region` con nombre | PASS |
| 1 FAIL en E2E: «Approved default» coincidía con dos textos | **CONFIRMED:** localizador ambiguo del test | `exact=True` | PASS |
| 3 errores de lint (ternarios anidados, línea larga) | Estilo | Reescritos | `npm run check` exit 0 |

## 8. Desviaciones, deuda y decisiones no autorizadas
- **Ubicación (DP-01):** «CER Route Configuration › Activity Emails», no «Settings › Notifications», porque esa sección no existe. **Necesita confirmación del PO.**
- **Quién aparece en Recipients:** las personas cuyo rol concede `route.worksession.execute`, es decir, quien tiene jornadas y actividades. Incluye owner, admin y route_admin, que también la tienen. Excluye `viewer` y `manager`. **Necesita confirmación del PO.**
- **«Correo verificado»:** la aplicación no verifica correos. Se exige un correo sintácticamente válido (sin DNS). Si CER quiere verificación real, es un cambio de identidad aparte.
- **Plantillas por defecto en el código, no sembradas** (sección 3).
- **Auditoría:** se guarda el asunto y el cuerpo anterior y nuevo de la plantilla. No son datos personales y `audit_event` tiene acceso controlado. Las preferencias guardan solo los booleanos cambiados; el usuario objetivo va en el resumen.
- **Textos de la interfaz en inglés,** como el resto del panel de administración. El banner de estado va en español, literal de §3.2, y el texto de los correos también.
- **Sin acción masiva** (§3.3) **ni preferencias por el propio empleado** (DP-04).

## 9. Prerrequisitos y recomendación para RTE-NOT-02/03
1. **Correo saliente configurado en DigitalOcean:** sigue pendiente desde antes. Hay que usar `app/core/email/backends.py` (SMTP o M365), no una dependencia nueva.
2. **Programación con `PlatformScheduler.register`:** ya tiene un candado para no enviar dos veces con varias réplicas. Mediodía según la zona horaria aplicable (**DP-02** pendiente). Fin de jornada = End Work + 20 min, aplazado si la jornada se reanuda.
3. **Idempotencia:** un registro de envío único por `(company, user, tipo, día local)`. Reutilizar el patrón de `missing_location_notification`.
4. **En el momento de enviar, volver a comprobar:** preferencia activa, pertenencia y cuenta activas, correo válido.
5. **Agregación:** actividades completadas, sin duplicados, por categoría; semana desde el lunes (**DP-03** pendiente).
6. **Escapado del contenido al enviar** (texto plano) y **pruebas de entrega real** antes de certificar.

## 10. Git y entrega
- Rama: `feature/rte-not-01-activity-emails` (desde `dev` `857a7d8`).
- Commit, push y MR: en el resumen de entrega.
- **Acción operativa al desplegar:** el PRE_DEPLOY aplica la migración 0021 y `converge` crea la capacidad. Luego hay que **asignar «Activityemails.Manage»** al rol que decida CER en Roles & Permissions.
  - Si la capacidad no aparece: `python -m app.db.scripts.converge` en la consola, como pasó con el mapa.
  - **En local:** `uv run alembic -c app/alembic.ini upgrade head` y `uv run python -m app.db.scripts.converge`, que **no** se ejecutaron sobre la base local.

## 11. Esfuerzo
Medido con `git diff --stat`: ≈2.650 líneas sin contar la instrucción.

| Tarea | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Backend: modelo, migración, servicio, API, validación | Hecho | ~1.040 LoC | backend, 175 LoC/h | 6,0 |
| Frontend: página, editor, destinatarios, accesibilidad | Hecho | ~880 LoC | UI, 60 LoC/h | 14,5 |
| Tests unitarios, integración y E2E | Hecho | ~690 LoC | mixto, ~120 LoC/h | 5,5 |
| **Total RTE-NOT-01** | Hecho | | | **≈26** |
| RTE-NOT-02/03: motor de envío (estimación) | No autorizado | ~1.200-1.600 LoC | integración, 80-100 LoC/h | 13-20, **+30 % por integración de correo = 17-26** |
