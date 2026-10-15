# CER Route — Jerarquía V1.6: el CEO lo ve todo, un mando no se vacía a mano, bajar de rango con «Replace manager»

**Reporte de implementación 001** · 15 de octubre de 2026
**Origen:** decisiones del PO del 15-10:
- el CEO ve todo sin tiempo;
- de COO hacia abajo, tiempo + relación;
- puede haber varios COO;
- los cambios solo por las vías habilitadas, para evitar el caso «lcerda → Rodrigo»;
- cubrir la bajada de rango.

**Status: COMPLETED WITH PENDING VALIDATION.** Validado en local, en la base de tests. Pendiente: la certificación de CER y el despliegue. **Sin migraciones ni datos tocados.**

---

## 1. Base y entornos

| Elemento | Valor |
|---|---|
| Base | `dev` @ `8fab9c0` (incluye V1.5, MR !94, desplegada en DigitalOcean) |
| Rama | `feature/hierarchy-ceo-full-history-and-guards`. No fusionada ni desplegada |
| Migraciones | **Ninguna nueva**: head `0020_org_replaces_user` |
| Base local | Copia de DigitalOcean actualizada por el desarrollador. **Solo lectura**: simulaciones en memoria |
| Script de corrección de datos | **Descartado.** El único relevo anterior a V1.5 es de CEO, y la regla nueva lo resuelve sin tocar datos |

## 2. Qué cambia

### 2.1 El CEO ve todo, sin tiempo
- **Qué ve:** todo el historial de toda la jerarquía, incluidas las personas que **ya salieron** (hasta su última asignación).
- **Lo que no cambia:** Today sigue mostrando solo a quien está.
- **De COO hacia abajo, sin cambios** (V1.5):
  - el sucesor hereda;
  - la primera asignación cubre el pasado;
  - los traslados laterales van por periodo.

**Comprobado sobre la copia local del entorno, solo lectura:** Rodrigo (CEO) pasa de **6** a **51** jornadas visibles. Las 5 restantes son del usuario `admin` (owner), que **nunca** estuvo en la jerarquía, y se excluyen correctamente.

### 2.2 Un mando no se vacía a mano — evita el caso «lcerda → Rodrigo»
- **La regla:** si un movimiento deja a un **CEO, COO o RM** sin **ningún** subordinado directo, se rechaza con 409 `manager_left_without_team`, y el mensaje indica «Replace manager» o «Retire manager».
- **Por dónde se aplica:**
  - Edit (cambio de superior o de rol fuera del árbol);
  - la API de organización (cambiar o quitar un cargo).
- **Lo que sigue permitido:**
  - trasladar **parte** del equipo;
  - que alguien **deje la compañía** o se **suspenda**.
- **El resultado:** el titular de un equipo solo cambia por **Replace manager**, que registra la sucesión. Ya no se puede suplantar una sustitución moviendo a la gente una a una.

### 2.3 Bajar de rango con «Replace manager»
- **Qué añade:** la opción «Keep [persona] in the company with a lower role». Se elige el **rol inferior** y **a quién reporta**; el sucesor puede ser su jefe.
- **Cómo se aplica:** en la misma transacción, el sucesor recibe el cargo y el equipo, y el saliente baja de rango con el rol de su nuevo cargo. Todo queda auditado con el mismo `operation_id`.
- **Rechazos, sin cambios en ningún caso:**
  - mismo nivel o superior;
  - quedar bajo sí mismo (ciclo);
  - Sales fuera de un CEO;
  - un rol fuera de la jerarquía (422).
- **Alcance de cada CEO, COO y RM:** es la misma operación, válida para los tres.
- **Tiempo:** **sin ajustes adicionales**. Bajar de rango cierra y abre periodos en T como cualquier cambio. Desde T, la persona ve según su nuevo puesto, y su historial como jefe pasa a su sucesor.

## 3. Vías habilitadas (resumen operativo)

| Cambio | Única vía |
|---|---|
| Alta de una persona (sin equipo) | Create user (CEO solo si no hay; COO y RM nuevos permitidos) |
| Traslado de Supervisor u OSM | Edit → Reports to (el nuevo jefe ve desde el traslado) |
| Rol entre Supervisor, OSM y Sales | Edit → lista |
| Cambiar al titular de un equipo (CEO, COO, RM) | Replace manager (hereda todo) |
| Bajar de rango a un mando | Replace manager → «Keep … with a lower role» |
| Cerrar un puesto con equipo | Retire manager |
| Vaciar un mando moviendo gente / ascender a CEO o COO por la lista | **Bloqueado** |

## 4. Pruebas

| Lote | Resultado |
|---|---|
| Jerarquía V1.3–V1.5 (`test_org_hierarchy`, `test_hierarchy_integrity_v14`) | **132/132 PASS** (ningún test existente vaciaba un mando) |
| Nuevos V1.6 (`test_hierarchy_v16`) | **13/13 PASS**: CEO sin enlace ve lo anterior al relevo; CEO ve a quien salió y Today no; RM por periodo; vaciar un mando, 4 vías → 409 sin cambios; salir y suspender, permitidos; COO → RM bajo el sucesor; CEO → COO (Sales al nuevo CEO, un CEO); 5 bajadas inválidas sin cambios; roles inferiores ofrecidos |
| E2E V1.6 (`test_hierarchy_v16_browser`) | **3/3 PASS**: sustituir y bajar de rango, en escritorio y móvil; aviso al vaciar un RM desde Edit |
| `npm run check` | 0 errores |
| Regresión completa: integración + contratos | **1327 PASS, 15 skipped, 1 FAIL** preexistente (`test_provisioning_alignment`: espera 12 capacidades para `route_admin` y hay 16 desde RTE09; decisión de CER), 920 s |
| Regresión completa: E2E | **203 PASS, 5 FAIL**: los 5 preexistentes de ubicación sin conexión de RTE06, los mismos nombres que en V1.4 y V1.5; el *diff* no toca ubicación ni la cola sin conexión. 3844 s |

## 5. Pendientes y decisiones

- **ftijerino (274): rol `supervisor`, cargo COO.**
  - Con V1.5 y V1.6 no se puede poner el rol COO desde la lista: está bloqueado por ser un ascenso a COO.
  - **Vía habilitada:** Replace manager **no aplica**, porque su puesto ya es COO.
  - **Propuesta:** permitir el cambio de rol cuando el cargo vigente **ya es** ese, porque es regularizar y no ascender. Unas 0,5 h. **Requiere tu decisión.**
- **jaleman (271) y lmuniz (272): rol `supervisor`, cargo RM.** Se regularizan desde Edit, con rol Regional Manager y el mismo Reports to.
- **Los 27 permisos del rol CEO:** sigue abierto.

## 6. Despliegue

- **Al fusionar:** no hay migración y no hay script. Que todos **recarguen la aplicación**.
- **Rollback:** revertir el código. No hay datos que deshacer.

## 7. Esfuerzo

| Tarea | Estado | Horas-agente |
|---|---|---|
| CEO sin tiempo, incluidas las personas que salieron | Hecho | 1,0 |
| Bloqueo de vaciar un mando | Hecho | 1,0 |
| Replace con baja de rango (servidor + pantalla) | Hecho | 2,5 |
| Tests de integración + E2E | Hecho | 2,0 |
| Regresión, informe, MR | En curso | 1,0 |
| **Total** | | **≈ 7,5 h** (estimado: 9,5) |
