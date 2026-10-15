# CER Route — Regularización de la jerarquía (rol/cargo) y readmisión de la CEO anterior

**Reporte 001** · 15 de octubre de 2026
**Origen:** el desarrollador pidió resolver desde local y después el MR: readmitir a lcerda como **COO bajo Rodrigo** y dejar coherente la jerarquía.
**Status: COMPLETED WITH PENDING VALIDATION.** Aplicado y verificado en la **base local** (copia del entorno compartido). **Pendiente:** ejecutar el mismo comando en DigitalOcean tras fusionar, y la certificación de CER.

---

## 1. Qué había

| Caso | Situación | Origen (auditoría, `CONFIRMED`) |
|---|---|---|
| ftijerino (274) | Rol `supervisor`, cargo **COO**, con lmuniz debajo | Cambios de rol por la pantalla general el 14-10 (antes de V1.4) |
| jaleman (271), lmuniz (272) | Rol `supervisor`, cargo **Regional Manager** | Ídem |
| lcerda (275) | **Retirada de la compañía** | «Replace manager» del 14-10 a las 22:31 (V1.4, cuando la sustitución siempre retiraba a quien salía); ejecutado por `ccordero` (route_admin), CEO sustituida por Rodrigo Test2 |

**Hueco de producto que impedía arreglar a ftijerino (`CONFIRMED`):** la regla de la V1.5 «CEO y COO solo por Replace manager» también bloqueaba dar el rol COO a quien **ya tenía** el cargo COO. Ninguna vía habilitada lo resolvía.

## 2. Qué se cambió

| Pieza | Cambio | Por qué |
|---|---|---|
| `organization/contract_guard.py` | El cambio de rol a CEO o COO se permite cuando el **cargo vigente ya es ese** y el superior no cambia (regularizar). Ascender por la lista sigue dando 409 | Cerrar el hueco sin abrir los ascensos |
| `app/db/scripts/regularize_hierarchy.py` (nuevo) | **Modo prueba por omisión.** `--aplicar` escribe con **los mismos servicios que la pantalla** (sin SQL a mano) y deja `audit_event` sin actor, con el motivo. Dos acciones: alinear el rol con el cargo (sin tocar cargo ni superior) y `--readmitir` (pertenencia + cargo en una transacción, como «Create user → Re-add») | Arreglo reproducible, auditado y ejecutable igual en DigitalOcean |
| `tests/integration/test_regularize_hierarchy.py` (nuevo) | 4 tests | Ver §4 |

Sin migraciones y sin cambios de frontend.

## 3. Ejecución en la base local (`db-dev-cer-route`)

| Paso | Resultado |
|---|---|
| Inventario previo (`hierarchy_preflight`) | 3 desajustes rol/cargo (271, 272, 274); 0 CEO duplicados; 0 superiores no válidos |
| Modo prueba de la alineación | 271 → Regional Manager · 272 → Regional Manager · 274 → COO (cargos sin tocar) |
| Modo prueba de la readmisión | 275 como COO bajo 267 |
| `--aplicar` (ambos) | APLICADO |
| Inventario posterior | **0 desajustes, 0 roles sin cargo, 0 superiores no válidos, 1 CEO** |
| Segunda ejecución | 0 desajustes (idempotente) |
| Auditoría | 5 eventos con el motivo «Hierarchy regularization by authorized command»: 3 `user/update`, 1 `org_assignment/assign`, 1 `user_company/reenroll` |
| Alcance de Rodrigo (CEO) | Sigue viendo **51** jornadas del historial; Today incluye ahora a lcerda |

**Estructura final:**

| Usuario | Rol | Cargo | Reporta a |
|---|---|---|---|
| test (Rodrigo) | CEO | ceo | — |
| ftijerino | COO | coo | Rodrigo |
| **lcerda** | **COO** | **coo** | **Rodrigo** |
| mgarcia, jaleman | Regional Manager | regional_manager | Rodrigo |
| lmuniz | Regional Manager | regional_manager | ftijerino |
| kaguirre, Xobando | Supervisor | supervisor | Rodrigo |

## 4. Pruebas

| Lote | Resultado |
|---|---|
| `test_regularize_hierarchy` | **4/4 PASS**: alinear (prueba sin cambios, aplicar, idempotente, auditoría, cargos intactos); la pantalla regulariza pero no asciende; readmitir a la ex CEO como COO; readmitir como segundo CEO → rechazo **sin dejar nada a medias** |
| Jerarquía + readmisión (`test_org_hierarchy`, `v14`, `v16`, `regularize`, `test_user_reenrollment`) | **168/168 PASS** |
| Ensayo previo en base de tests (desechable) | La ex CEO retirada por Replace → Create user → `same_tenant_removed` → readmisión COO, 200 |
| Regresión de integración completa + contratos | **1331 PASS, 15 skipped, 1 FAIL** preexistente (`test_provisioning_alignment`: espera 12 capacidades para `route_admin` y hay 16 desde RTE09; decisión de CER), 1213 s |
| E2E de jerarquía y alta/readmisión (`test_org_hierarchy_browser`, `v14`, `v16`, `test_user_creation_browser`) | **23/23 PASS**, 399 s. Los E2E completos (incluidos los 5 preexistentes de RTE06) **NOT RUN**: sin cambios de frontend |

## 5. Hallazgo

**El rol CEO tiene ahora 29 capacidades en la base local**, frente a las 27 anteriores. El despliegue ejecutó `converge`, que **añade** las 2 de Reports de la plantilla. No quita las 25 que no son de la plantilla, porque `converge` nunca revoca. Sigue abierto el sobreprivilegio del CEO: decisión de CER.

## 6. Qué hacer en DigitalOcean (tras fusionar y desplegar)

En la consola de la app:
```
python -m app.db.scripts.hierarchy_preflight
python -m app.db.scripts.regularize_hierarchy --compania 1
python -m app.db.scripts.regularize_hierarchy --compania 1 --aplicar
python -m app.db.scripts.regularize_hierarchy --compania 1 --readmitir lcerda@cermanagementgroup.com --rol COO --superior test@test.com
python -m app.db.scripts.regularize_hierarchy --compania 1 --readmitir lcerda@cermanagementgroup.com --rol COO --superior test@test.com --aplicar
python -m app.db.scripts.hierarchy_preflight
```
Revisa cada modo prueba antes de su `--aplicar`. El último inventario debe dar 0 desajustes. Alternativa sin consola para lcerda: «Create user → Re-add» en CER Route → Users (mismo resultado).

**Rollback:**
- **Alineación:** volver a poner el rol anterior desde CER Route → Users. La auditoría guarda el `role_id` anterior.
- **Readmisión:** retirar de nuevo a lcerda desde la pantalla, porque no tiene equipo.

## 7. Esfuerzo

| Tarea | Horas-agente |
|---|---|
| Ajuste de la guarda + script + tests | 2,0 |
| Ensayo, ejecución y verificación local | 0,5 |
| Regresión, informe, MR | 0,5 |
| **Total** | **≈ 3 h** |
