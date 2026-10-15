# CER Route — El Superadmin aplica permisos sin pasar por aprobación

**Reporte 001** · 15 de octubre de 2026
**Origen:** decisión del desarrollador y de CER: «el nivel de super admin debería tener todos los permisos y no debería pasar por el canal de aceptación; el super admin tiene que estar por encima de cualquier permiso y rol».
**Status: COMPLETED WITH PENDING VALIDATION.** Validado en local, en la base de tests. Pendiente: certificación de CER y despliegue.

## 1. Qué es el «Superadmin» (revisado en la base local)
- Es el **superusuario de plataforma** (`user.is_superuser = true`). La pantalla rotula «Superadmin» a quien lo es.
- En la base local solo lo es **`admin`** (Application Administrator). `test` (Rodrigo) y `ccordero` no lo son.
- **Ya tenía todos los permisos:** `require_permissions`, `require_page_permissions` y `hasUserPermission` le dejan pasar en todo, mapa incluido.
- **Lo único que le aplicaba era la aprobación por dos personas** en Roles & Permissions: su cambio quedaba pendiente y nadie, ni él, podía aprobar lo suyo.

## 2. Qué cambia
| Pieza | Cambio |
|---|---|
| `rolepermissionsapprovals/service.py` | `apply_direct`: aplica el conjunto al momento. Deja una solicitud **`approved`** con el Superadmin como solicitante y revisor («Applied directly by the platform superadmin») y un **`audit_event`** `role_permission/apply_direct` con lo concedido y lo revocado. Una solicitud pendiente de otra persona sobre ese rol se cierra como `rejected` («Superseded by a direct change of the platform superadmin»). Se reutilizan la validación y la aplicación del flujo existente (`_validar`, `_aplicar`) |
| `roles/router.py` | `PUT /api/roles/{id}/permissions`: si quien llama es `is_superuser`, `apply_direct`; si no, el flujo de siempre |
| `RolePermissionsPanel.tsx` | Para el Superadmin: botón «Apply changes», aviso «Applied immediately (platform superadmin).», y se puede guardar aunque haya una solicitud pendiente |
| `docs/ARCHITECTURE.md` | Control de cambios de permisos actualizado |

**Sin cambios para el resto:** el rol `owner` y todos los demás siguen con la aprobación de dos personas. Sin migraciones y sin datos tocados.

## 3. Pruebas
| Lote | Resultado |
|---|---|
| `test_superadmin_direct_permissions` (nuevo): aplica al momento y queda trazado; sustituye una pendiente; el owner sigue pendiente; sin cambios → 400 | **4/4 PASS** |
| `test_maker_checker` (existente) | **9/9 PASS** |
| E2E nuevo: Superadmin en Roles & Permissions («Apply changes», sin pendiente) | **1/1 PASS** |
| E2E de seguridad y roles (jerarquía, UX admin, ciclo de vida, acceso) | **26/26 PASS** |
| Integración completa | **1344 PASS, 15 skipped, 2 FAIL** — ver abajo |
| `npm run check` / build | 0 errores / OK |
| E2E completos | **NOT RUN**: el cambio de frontend se limita al panel de permisos, cubierto arriba |

**Fallos, ninguno causado por este cambio:**
- **`test_provisioning_alignment::…twelve_and_two_capabilities`:** preexistente desde RTE09, porque espera 12 capacidades para `route_admin` y hay 16.
- **`test_route_roles_migration::test_la_bajada_se_detiene_si_hay_cargos_sales`:** **carrera preexistente entre tests**, causa `CONFIRMED`.
  - `test_route_notes_migration_safety` (30-09) crea temporalmente una migración `roundtrip_check` en `app/migrations/versions/` para comprobar el autogenerate. Si otro test que corre en paralelo ejecuta `alembic upgrade head` en ese instante, sube a esa revisión temporal (`74141788ff7f`).
  - **Ejecutado aislado, pasa (6/6).**
  - **Recomendación aparte:** generar esa revisión de prueba en un directorio temporal.

## 4. Riesgo que conviene asumir conscientemente
Sin la aprobación de dos personas, **una sola cuenta puede cambiar los permisos de cualquier rol sin revisión previa**. Queda trazado (Permission Requests + auditoría), pero no hay control previo. Recomendación: la cuenta Superadmin, personal y protegida (contraseña fuerte, no compartida).

## 5. Despliegue
Al fusionar no hay migración ni script. Con `admin` (Superadmin): **Roles & Permissions → rol → marcar «Activity.Map.Read» → Apply changes**, y queda concedido al momento.

## 6. Esfuerzo
≈ **2,5 horas-agente**: servicio, endpoint, panel, 5 tests y la regresión.
