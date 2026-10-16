# CER Route — RTE07 · Corrección del acceso del Administrador
## Reporte 003

**Instrucción:** `CER_ROUTE_RTE07_ADMIN_ACCESS_CORRECTION_INSTRUCTIONS_003.md`
**Rama:** `fix/rte07-admin-access-correction` (desde `dev`)
**Fecha:** 2026-10-06

---

## 1. Resultado ejecutivo

El defecto es real, está reproducido **sobre datos reales** y corregido. Pero no
estaba donde parecía.

**El código de RTE07 estaba bien.** La capacidad `route.live.read` existe una
sola vez en el catálogo, la plantilla del Administrador la incluye, y los tres
guardas —menú, página y API— exigen exactamente esa capacidad. Nada de eso
falló.

Lo que faltaba era el puente entre el catálogo y los tenants que ya existían:

> `seed_permissions` alinea la tabla de capacidades, que es **global**.
> `seed_roles` alinea las concesiones de **una sola compañía**: la que nombra
> `BOOTSTRAP_COMPANY_SUBDOMAIN`, que por defecto es `cer`.

Así que una capacidad introducida **después** de que un tenant existiera llegaba
al catálogo de toda la instalación y nunca a su rol. Y no había camino soportado
para corregirlo: sólo editar la base a mano.

**La prueba más dura no es un test, es la base de datos.** Ejecutado contra el
tenant real de desarrollo, el comando nuevo encontró esto:

```text
+ 3 capacidades creadas (27 en el catálogo)
+ cerroute · route_admin -> route.live.read        <- el defecto reportado
+ cerroute · route_admin -> route.activity.read    <- RTE08, el mismo hueco
+ cerroute · owner  -> route.live.read, route.activity.read, route.odometer.selfapprove
+ cerroute · admin  -> route.live.read, route.activity.read, route.odometer.selfapprove
  concesiones añadidas: 8
```

El tenant se llama **`cerroute`**; el bootstrap apunta por defecto a **`cer`**.
Ahí está el defecto, entero, en una línea.

Por eso la corrección no arregla una capacidad: **arregla el camino**. Un
mecanismo de alineación idempotente, que sólo añade, que deja rastro en
auditoría y que alcanza **todas** las compañías.

---

## 2. El defecto de campo, reproducido

Reproducido de dos formas independientes.

**En test, de punta a punta.** Se quita la concesión a `route_admin` —que es
exactamente el estado de un tenant creado antes de RTE07, porque la fila de
`permission` existe y la concesión no— y entonces:

```text
capacidades efectivas del Administrador   ->  sin route.live.read
GET /api/live/today                       ->  403
GET /admin/route/today                    ->  denegada
menú lateral                              ->  sin "Today / Live"
```

**En la base de datos real de desarrollo**, sin simular nada: el comando de
alineación encontró que `route_admin` del tenant `cerroute` **no tenía**
`route.live.read`, y que tres filas de capacidad ni siquiera existían en la
tabla `permission`.

---

## 3. Usuario afectado y rol efectivo

| Pregunta | Respuesta |
|---|---|
| ¿La cuenta es `route_admin` o un `admin` del núcleo? | **No cambia la respuesta** |
| Plantilla de `route_admin` | 14 capacidades, `route.live.read` incluida |
| Plantilla de `admin` del núcleo | **26 de 27** (todas menos `roles.delete`), `route.live.read` incluida |
| Plantilla de `owner` | **27 de 27** |
| `manager`, `viewer`, `supervisor` | **no** la tienen, y no deben tenerla |

§2 manda **parar** si la cuenta afectada resultara ser un `admin` del núcleo y
sostenerla exigiera cambiar el modelo de roles. **No lo exige**, y está probado
con un test propio: un `admin` del núcleo sin la concesión recibe 403, y tras la
alineación recibe 200. Mismo hueco, mismo arreglo, sin tocar el modelo.

Por eso este checkpoint **no se declara bloqueado**: la corrección no depende de
cuál de los dos roles tenga la cuenta de CER. Si CER quiere, puede decirme el
usuario exacto y lo confirmo contra su tenant; el arreglo es el mismo.

---

## 4. Causa raíz

```text
observado    El Administrador no ve ni abre Today / Live.

esperado     route_admin tiene route.live.read -> menú visible, página servida,
             API autorizada, datos del propio tenant.

causa real   EXISTING TENANT PROVISIONING GAP  (`CONFIRMED`)

             `seed_permissions` alinea la tabla `permission`, que es global.
             `seed_roles` concede sólo en la compañía que resuelve
             `BOOTSTRAP_COMPANY_SUBDOMAIN` (`cer` por defecto; el tenant real
             es `cerroute`). Una capacidad introducida después de que el tenant
             existiera no tenía ningún camino soportado hasta su rol.

             Agravante medido, `DEPLOYMENT / DATA DRIFT` (`CONFIRMED` en local):
             en la base de desarrollo faltaban además **tres filas** de la
             tabla de capacidades, de RTE06, RTE07 y RTE08. Es decir, no se
             había ejecutado ningún aprovisionamiento desde entonces.

corrección   `app/db/scripts/align_role_capabilities.py`: alinea el catálogo y
             después concede a cada rol de plantilla, **en cada compañía**, lo
             que le falte. Sólo añade, es idempotente y queda auditado.

prueba       Contra la base real: 8 concesiones añadidas en la primera
             ejecución, **0** en la segunda. En test: el Administrador pasa de
             403 a 200 y de no ver el menú a verlo, en la misma sesión.
```

Lo que **no** era: no era un hueco de la plantilla, ni del menú, ni del guarda
de página, ni del guarda de API. Los cuatro estaban bien y hay un test que los
fija para que sigan estándolo.

---

## 5. Catálogo y concesiones

| Comprobación | Resultado |
|---|---|
| `route.live.read` existe una sola vez en el catálogo | **sí** |
| Está adscrita a una superficie protegida | **sí**: API, página y menú |
| La plantilla de `route_admin` la incluye | **sí** |
| ¿Se creó una segunda capacidad con otro nombre? | **no**, y un test lo impide |
| ¿Se cambió alguna plantilla de rol? | **no** |
| ¿Se tocó el modelo de roles del núcleo? | **no** |

Un test comprueba además que, tras la alineación, **ningún rol acaba con
capacidades que su plantilla no declara**. Es la forma precisa de «no se
reutilizaron los roles del núcleo»: el mecanismo aplica las plantillas tal como
están y nada más.

> Una corrección propia, por si ayuda a leer el reporte: la primera versión de
> ese test afirmaba que ningún rol del núcleo debía tener `route.live.read`, y
> era **falso** — `owner` recibe las 27 capacidades del catálogo por plantilla y
> `admin` todas menos una, desde antes de RTE07. Se corrigió la aserción, no el
> producto.

---

## 6. Aprovisionamiento de tenants existentes

El escenario que §7 pide validar, ejecutado:

| Paso | Resultado |
|---|---|
| 1. Tenant anterior a `route.live.read` | reproducido (y encontrado en la base real) |
| 2. `route_admin` ya existía | sí |
| 3. La capacidad se introduce | catálogo global |
| 4. Se ejecuta la alineación soportada | `uv run python -m app.db.scripts.align_role_capabilities` |
| 5. El `route_admin` existente la recibe | **sí** |
| 6. Repetir no duplica ni cambia nada más | **sí**: 0 concesiones, sin filas duplicadas |

Decisiones de diseño que conviene que CER conozca:

* **No revoca nunca.** Misma semántica que el bootstrap y por la misma razón: un
  tenant tiene decisiones reales dentro, y quitar por su cuenta lo que un
  administrador concedió sería destruir trabajo sin avisar. Retirar una
  capacidad obsoleta sigue siendo un script explícito, como el que ya existe
  para `roles.read`.
* **No crea roles.** Si una compañía no tiene un rol de plantilla, se **informa**
  y no se inventa: un rol nuevo aparece en la pantalla de permisos de ese
  tenant, y eso es decisión suya.
* **No toca usuarios ni asignaciones.**
* **Deja rastro**: cada concesión se registra en `audit_event`, sin actor,
  porque no la pidió una persona desde una pantalla.
* **Reutiliza** el paso de catálogo del bootstrap en vez de copiarlo: dos
  implementaciones de la misma alineación acabarían diciendo cosas distintas.

---

## 7. Alineación de menú, página y API

Las tres capas dependen de **la misma** capacidad, y hay un test que lo fija
leyendo las tres declaraciones:

```text
API      app/routers_api/live/router.py        require_permissions(["route.live.read"])
Página   app/routers_pages/admin/route/router.py  require_page_permissions(["route.live.read"])
Menú     navigation.ts                          requiredPermission: 'route.live.read'
```

El menú es **dirigido por capacidad**, no por nombre de rol: no hay ningún
`if role == route_admin` en ninguna parte.

Y un hecho operativo que importa y que se midió en vez de suponerse: **no hace
falta volver a iniciar sesión.** La cookie que pinta el menú se recalcula contra
la base en cada petición, así que basta recargar. El test de navegador lo
demuestra sobre la misma sesión abierta: antes no ve el menú, se ejecuta la
alineación, recarga, y entra.

---

## 8. Corrección aplicada

| Archivo | Qué es |
|---|---|
| `app/db/scripts/align_role_capabilities.py` | **nuevo**: el mecanismo de alineación |
| `tests/integration/test_rte07_admin_access.py` | **nuevo**: 11 tests |
| `tests/e2e/test_rte07_admin_access_browser.py` | **nuevo**: 2 tests de navegador |

**No se modificó ni un archivo existente.** Ni el código de RTE07, ni el
catálogo, ni las plantillas de rol, ni el menú, ni los guardas, ni el bootstrap.
La corrección es puramente aditiva: +751 líneas, −0.

---

## 9. Validación negativa del Supervisor

| Comprobación | Resultado |
|---|---|
| `route.live.read` en sus capacidades efectivas | **no** |
| `GET /api/live/today` | **403** |
| Página directa por URL | **denegada** |
| «Today / Live» en su menú | **no aparece** |

Verificado **después** de ejecutar la alineación, que es cuando tiene sentido
preguntarlo: lo que había que descartar es que arreglar al Administrador
ensanchara al Supervisor.

---

## 10. Aislamiento entre tenants

El Administrador de alpha, tras la alineación, no recibe ni un supervisor de
beta. Y el alcance sigue saliendo del subdominio, nunca de la petición.

La alineación alcanza a **las dos** compañías —es su propósito— y eso no mezcla
nada: concede capacidades al rol de cada tenant, que es a quien pertenece.

---

## 11. Regresión

| Lote | Tests | Resultado | Exit | Tiempo |
|---|---:|---|---:|---|
| Corrección (integración, nuevo) | 11 | **11 PASS** | 0 | 17 s |
| Corrección (navegador, nuevo) | 2 | **2 PASS** | 0 | 37 s |
| RTE07 completo: integración, navegador, frescura y capturas | 25 | **25 PASS** | 0 | 358 s |
| RBAC y redes: catálogo, página, navegación, superficie pública, + RTE08 | 80 | **80 PASS** | 0 | 73 s |
| Autoridad de roles de Route y reinscripción de usuarios | 32 | **32 PASS** | 0 | 48 s |
| `import app.db.scripts.align_role_capabilities` | — | **OK** | 0 | — |
| Comando contra la base real, dos veces | — | **8 → 0** concesiones | 0 | — |

**La UX de Today / Live no cambió**: no se tocó ni un archivo de interfaz, y las
capturas de RTE07 siguen siendo válidas.

Frontend: **NOT APPLICABLE**. Migraciones: **NOT APPLICABLE** — no hay cambio de
esquema.

---

## 12. Esperado → Implementado → Evidencia → Hueco

| AC | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | Causa raíz demostrada con evidencia | **VALIDATED** | §4; 8 concesiones en la base real |
| 2 | Un `route_admin` tiene `route.live.read` | **VALIDATED** | test de alineación |
| 3 | Today / Live visible en navegación normal | **VALIDATED** | navegador, misma sesión |
| 4 | La página abre | **VALIDATED** | navegador |
| 5 | La API responde | **VALIDATED** | 403 → 200 |
| 6 | Los tenants existentes quedan cubiertos | **VALIDATED** | §6, los 6 pasos |
| 7 | Sin parche manual de base como solución normal | **VALIDATED** | comando soportado, idempotente y auditado |
| 8 | El Supervisor sigue denegado | **VALIDATED** | §9, API y navegador |
| 9 | Aislamiento entre tenants intacto | **VALIDATED** | §10 |
| 10 | Roles del núcleo no reutilizados | **VALIDATED** | §5; ningún rol excede su plantilla |
| 11 | Comportamiento de RTE07 sin cambios | **VALIDATED** | 25/25; cero archivos de interfaz tocados |
| 12 | Regresión afectada verde | **VALIDATED** | §11 |
| 13 | Sin `PARTIAL`/`GAP`/`BLOCKED`/decisión pendiente | **VALIDATED** | §13 |

**Hueco dentro de esta corrección: ninguno.**

---

## 13. Asuntos restantes

**Dentro de la corrección: ninguno.**

**Acción operativa — ésta es la que cierra el defecto en el entorno
compartido.** Lo que hice es local; **local no es compartido**:

```bash
uv run python -m app.db.scripts.align_role_capabilities
```

Hay que ejecutarlo **en el entorno desplegado**. Hasta entonces el
Administrador seguirá sin ver Today / Live allí, por mucho que el código esté
bien. El comando dirá exactamente qué concedió, y una segunda ejecución no hará
nada.

Sustituye a la acción que había reportado antes para RTE08 —«sembrar
`route.activity.read` con bootstrap»—: este comando concede **las dos**, y no
crea una compañía nueva por error si `BOOTSTRAP_COMPANY_SUBDOMAIN` no está
puesto.

**Recomendación, no ejecutada por no estar en el alcance:** añadir ese comando
al runbook de despliegue, después de las migraciones. El hueco se abre cada vez
que un checkpoint introduce una capacidad, y ya ocurrió tres veces seguidas
—RTE06, RTE07 y RTE08— sin que nadie lo notara hasta que CER usó la pantalla.
No lo conecté al arranque de la aplicación a propósito: conceder autorizaciones
sola, en cada despliegue y sin que nadie lo decida, es un cambio mayor que el
que esta instrucción autoriza.

**Hallazgo incidental, reportado donde aparece:** `BOOTSTRAP_COMPANY_SUBDOMAIN`
sigue sin estar puesto en el entorno desplegado —ya estaba en la lista de deuda
abierta—. Con el comando nuevo deja de ser la causa de este defecto, pero sigue
siendo un riesgo: un bootstrap ejecutado sin esa variable **crea una compañía
`cer` nueva** en vez de alinear `cerroute`.

---

## 14. Estado propuesto

```text
RTE07 ADMIN ACCESS CORRECTION COMPLETE / READY FOR CER VALIDATION
```

Causa raíz demostrada sobre datos reales, corrección soportada e idempotente,
tenants existentes cubiertos, Supervisor y roles del núcleo intactos, RTE07 sin
cambios y regresión verde.

**No se declara el checkpoint cerrado de nuevo**: la certificación del delta
correctivo es de CER.

---

## 15. Estimación del esfuerzo

| Componente | Líneas |
|---|---|
| `align_role_capabilities.py` | 204 |
| Tests de integración (11) | 400 |
| Tests de navegador (2) | 147 |
| **Total** | **751 / −0** |

| Tarea | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Diagnóstico D1–D6 y clasificación de la causa | `DONE` | lectura y medición | análisis | 1,2 |
| Reproducción del defecto (test y base real) | `DONE` | — | backend | 0,6 |
| Mecanismo de alineación | `DONE` | ~204 LoC | backend/dominio | 1,2 |
| Tests de integración | `DONE` | ~400 LoC | backend | 2,4 |
| Tests de navegador | `DONE` | ~147 LoC | UI/navegador | 2,4 |
| Regresión por lotes | `DONE` | 150 tests | ejecución | 1,0 |
| Reporte 003 | `DONE` | — | documentación | 0,5 |
| **Subtotal ejecutado** | | | | **9,3** |
| Margen de riesgo (+10%, determinista) | | | | **+0,9** |
| **Total del delta** | | | | **≈ 10,2 h-agente** |

Margen determinista y no de navegador: el grueso es backend y datos, y la parte
de navegador es pequeña y ya estaba resuelta por el arnés existente.

---

## 16. Siguiente paso

Ejecutar el comando en el entorno compartido y validar con la cuenta real de
CER. **No se inicia ni se modifica RTE08, no se reanuda RTE10-A01 y no se
promueve trabajo no relacionado.**
