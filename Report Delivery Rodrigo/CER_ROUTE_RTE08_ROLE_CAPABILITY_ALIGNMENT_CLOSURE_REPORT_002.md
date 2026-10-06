# CER Route — RTE08 · Cierre: alineación de capacidades de rol
## Reporte 002

**Instrucción:** `CER_ROUTE_RTE08_ROLE_CAPABILITY_ALIGNMENT_CLOSURE_INSTRUCTIONS_002.md`
**Rama:** `fix/rte08-role-capability-alignment` (desde `dev`, con el alineador ya fusionado)
**Fecha:** 2026-10-06
**No sustituye al reporte 001**, lo completa y corrige su acción operativa.

---

## 1. Resultado ejecutivo

El hueco de aprovisionamiento está cerrado para Activity Explorer, con el
**mismo mecanismo compartido** que corrigió Today / Live. No se creó ningún
parche específico de RTE08: eso es justo lo que §3 pide no hacer.

Lo que se añadió es evidencia para esta capacidad —el ciclo completo del tenant
existente, la paridad de las tres capas, el negativo del Supervisor y el
aislamiento— y la corrección de la instrucción operativa que el reporte 001
daba mal.

Dos cosas que conviene leer aunque el resultado sea verde:

* **Un test mío pasaba sin comprobar nada.** El negativo del Supervisor
  localizaba el enlace del menú con `exact=True`, y el nombre accesible real es
  `Activity CER Route`: habría dado cero aunque el enlace estuviera ahí.
  Corregido, y ahora el positivo usa el mismo localizador, que es lo que lo
  convierte en control.
* **La fragilidad del arnés sigue viva y la medí.** Un lote que mezcla varios
  módulos produce `fixture 'seeded' not found`. Lo reproduje **sólo con
  archivos de `dev`**, sin ninguno mío, así que es preexistente y no una
  regresión — pero condiciona cómo se ejecuta la regresión y por eso va en §10
  y no escondido.

---

## 2. Causa raíz confirmada

```text
observado    Un Administrador de un tenant existente no ve Activity y recibe
             403 en la página y en la API.

esperado     Su plantilla declara route.activity.read -> menú visible, página
             servida, API autorizada, datos de su propio tenant.

causa        EXISTING TENANT PROVISIONING GAP, la misma que Today / Live.
             `seed_permissions` alinea la tabla de capacidades, que es global;
             `seed_roles` concede sólo en la compañía que resuelve
             BOOTSTRAP_COMPANY_SUBDOMAIN. Una capacidad introducida después de
             que el tenant existiera llegaba al catálogo y nunca a su rol.

corrección   Ninguna nueva: el mecanismo compartido
             `app/db/scripts/align_role_capabilities`, ya fusionado en `dev`.
             Este delta lo **verifica** para route.activity.read y corrige la
             documentación.

evidencia    §4, §5, §6 y la ejecución contra el tenant real.
```

El estado de partida que §3 pide asumir se confirmó punto por punto:

| Comprobación | Resultado |
|---|---|
| Catálogo de capacidades | **correcto** |
| Plantillas de rol | **correctas** |
| Guarda de navegación | **correcto** |
| Guarda de página | **correcto** |
| Guarda de API | **correcto** |
| Concesiones de tenants existentes | **desalineadas** |
| Camino de alineación | **ya corregido**, y aquí verificado |

---

## 3. Matriz de capacidad y plantillas

`route.activity.read` existe **una sola vez**, en el código y en la tabla.

| Rol | ¿Declara `route.activity.read`? | Nota |
|---|---|---|
| `route_admin` | **sí** | el Administrador de CER Route |
| `supervisor` | **no** | y no debe; ejecuta su jornada, no explora la de los demás |
| `manager` | no | — |
| `viewer` | no | — |
| `owner` | **sí** | por su plantilla existente: recibe las 27 del catálogo |
| `admin` | **sí** | por su plantilla existente: 26 de 27 |

`owner` y `admin` la declaran **desde antes** de RTE08 y eso **se preserva**:
§5 lo pide de forma explícita, y quitarla para forzar una lectura de dos roles
sería inventar una regla que nadie aprobó.

El invariante queda fijado por un test: tras alinear, **ningún rol acaba con
capacidades que su plantilla no declare**.

---

## 4. Reproducción del tenant existente

Los once pasos de §7, ejecutados en orden dentro de un solo test:

| Paso | Aserción | Resultado |
|---|---|---|
| 1–4 | Tenant con el rol antiguo; la fila de `permission` existe y la concesión no | reproducido |
| 4 | Capacidades efectivas del Administrador | **sin** `route.activity.read` |
| 4 | `GET /api/activity-explorer` | **403** |
| 4 | `GET /admin/route/activity` | **denegada** |
| 5–6 | Se ejecuta el alineador | **≥1** concesión añadida |
| 7 | «Activity» en la navegación | **visible** (§7, navegador) |
| 8 | La página abre | **200** |
| 9 | La API devuelve datos autorizados | **200**, con `supervisors` |
| 10–11 | Segunda ejecución | **0** concesiones, sin cambios |

Y en el navegador, sobre **una sola sesión**: antes no ve el menú ni abre la
página; se alinea; **recarga sin volver a entrar**; el menú aparece y el
explorador carga con su contenido real —encabezado `Activity`, el subtítulo
aprobado y las mini-estadísticas del día.

Que no haga falta cerrar sesión no es un detalle de comodidad: §9 pide
expresamente no exigirlo salvo que la arquitectura lo imponga. **No lo impone**,
porque la cookie que pinta el menú se recalcula contra la base en cada petición.
Está medido, no supuesto.

---

## 5. Ejecución de la alineación

Contra el tenant real de desarrollo, en la entrega anterior:

```text
+ cerroute · route_admin -> route.activity.read     <- esta capacidad
+ cerroute · route_admin -> route.live.read
+ cerroute · owner/admin -> ambas, y route.odometer.selfapprove
  concesiones añadidas: 8
```

Y en este delta, sobre el mismo tenant ya alineado:

```text
  compañías revisadas  : 1
  concesiones añadidas : 0
  = nada que añadir: todo estaba alineado.
```

Comportamiento del mecanismo, verificado con tests propios en este delta:

* **opera sobre todas las compañías** existentes;
* **nunca revoca**;
* **no crea roles**: una compañía sin un rol de plantilla se **informa**. Un
  test crea una compañía sin roles y comprueba que se reportan los seis
  ausentes y que no se crea ninguno;
* **sólo añade lo que la plantilla declara**: un test comprueba que la
  diferencia antes/después es exactamente `{route.activity.read}`;
* **es idempotente**;
* **deja rastro** en `audit_event`, sin actor, porque no lo pidió una persona
  desde una pantalla;
* **reutiliza** el paso de catálogo del bootstrap en vez de duplicar
  definiciones.

---

## 6. Idempotencia

| Ejecución | Concesiones añadidas |
|---|---:|
| Primera, sobre el tenant desalineado | ≥ 1 |
| Segunda, inmediatamente después | **0** |
| Sobre el tenant real `cerroute`, ya alineado | **0** |

Y sin filas duplicadas para el mismo par rol/capacidad.

---

## 7. Paridad de navegación, página y API

Las tres capas dependen de **la misma** capacidad, y un test lo fija leyendo
las tres declaraciones:

```text
API      app/routers_api/activityexplorer/router.py   require_permissions(["route.activity.read"])
Página   app/routers_pages/admin/route/router.py      require_page_permissions(["route.activity.read"])
Menú     navigation.ts                                requiredPermission: 'route.activity.read'
```

| Actor | Navegación | Página | API |
|---|---|---|---|
| Con la capacidad | **visible** | **200** | **200** |
| Sin la capacidad | **no se ofrece** | **denegada** | **403** |

El menú es dirigido por capacidad: no hay ningún `if role == route_admin` en
ninguna parte.

---

## 8. Validación negativa del Supervisor

| Comprobación | Resultado |
|---|---|
| `route.activity.read` en sus capacidades efectivas | **no** |
| `GET /api/activity-explorer` | **403** |
| Página directa por URL | **denegada** |
| «Activity» en su menú | **no aparece** |

Verificado **después** de alinear, que es cuando tiene sentido preguntarlo.

> **Un defecto de test, encontrado y corregido.** La primera versión de esta
> comprobación en el navegador buscaba el enlace con `exact=True`, y el nombre
> accesible real es `Activity CER Route`. Habría dado cero aunque el enlace
> estuviera: un verde sin contenido. Ahora se localiza por subcadena, y el test
> positivo usa **el mismo** localizador — eso es lo que convierte el cero en
> evidencia.

---

## 9. Aislamiento entre tenants

Con las dos compañías alineadas:

* el Administrador de alpha no recibe **ni un** supervisor de beta;
* pedir el supervisor de beta por identificador devuelve **404**, no 403:
  confirmar que existe ya sería decir algo de otro tenant;
* el alcance sigue saliendo del subdominio, nunca de la petición.

Alinear las dos compañías no mezcla nada: concede capacidades al rol de cada
tenant, que es a quien pertenecen.

---

## 10. Regresión de RTE08

| Lote | Tests | Resultado | Exit | Tiempo |
|---|---:|---|---:|---|
| RTE08 completo: integración + navegador + capturas | 26 | **26 PASS** | 0 | 174 s |
| Alineación de RTE08 (nuevo, integración) | 8 | **8 PASS** | 0 | 24 s |
| Acceso a Activity (nuevo, navegador) | 2 | **2 PASS** | 0 | 27 s |
| Alineación compartida de RTE07 | 11 | **11 PASS** | 0 | 17 s |
| Autoridad de roles de Route | 13 | **13 PASS** | 0 | 15 s |
| Redes: catálogo, página, navegación, superficie pública | 63 | **63 PASS** | 0 | 5 s |

**La UX de Activity Explorer no cambió**: no se tocó ni un archivo de interfaz
ni del contrato de lectura. Las capturas del reporte 001 siguen siendo válidas.

Migraciones: **NOT APPLICABLE**. Frontend: **NOT APPLICABLE**.

### Hallazgo: la fragilidad del arnés, medida

Un lote que mezcla varios módulos produce `fixture 'seeded' not found` en el
último de ellos. Lo importante es la clasificación, y está hecha con evidencia:

```text
mis dos archivos solos                      -> 8 y 2 PASS
mis archivos + test_route_role_authority    -> 21 PASS
el lote grande SIN ninguno de mis archivos  -> fixture 'seeded' not found
```

La tercera línea es la que decide: **se reproduce con archivos que ya estaban en
`dev`**. Es deuda técnica preexistente, no una regresión de este delta, y no
esconde ningún fallo de producto: todas las suites corren verdes por la
agrupación soportada —invocaciones separadas— que es como se ejecutó la
regresión de arriba.

No se convirtió este delta en una refactorización del arnés: la instrucción
anterior lo prohíbe explícitamente y ésta no lo autoriza.

---

## 11. Corrección de la instrucción operativa

**Antes** (reporte 001, §18 y §21):

```bash
uv run python -m app.db.scripts.bootstrap
```

**Ahora**:

```bash
uv run python -m app.db.scripts.align_role_capabilities
```

Por qué el primero no sirve para esto, con precisión:

* alinea las concesiones de **una sola** compañía, la que resuelve
  `BOOTSTRAP_COMPANY_SUBDOMAIN`;
* esa variable **no está puesta** en el entorno desplegado, así que resolvería
  a `cer` — y el tenant real es `cerroute`;
* peor: no la encontraría y **crearía una compañía nueva** llamada `cer`, con
  su administrador inicial, en vez de alinear la existente.

El reporte 001 **no se sobrescribió**. Se le añadió un aviso de supersesión al
principio, acotado a la acción operativa, para que nadie ejecute el comando
equivocado leyéndolo. El resto del documento queda tal como se entregó; si CER
prefiere que el 001 quede intacto sin esa nota, se retira.

---

## 12. Esperado → Implementado → Evidencia → Hueco

| AC | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | La causa sigue siendo la alineación de tenants existentes | **VALIDATED** | §2 |
| 2 | `route.activity.read` existe una sola vez | **VALIDATED** | §3, código y tabla |
| 3 | `route_admin` la recibe por el camino compartido | **VALIDATED** | §4 |
| 4 | El Supervisor sigue sin ella | **VALIDATED** | §8 |
| 5 | Los demás roles siguen sus plantillas | **VALIDATED** | §3; ningún rol excede su plantilla |
| 6 | Tenants existentes alineados sin tocar la base a mano | **VALIDATED** | §5 |
| 7 | El proceso es idempotente | **VALIDATED** | §6 |
| 8 | Ningún rol se crea en silencio | **VALIDATED** | §5, test de compañía sin roles |
| 9 | Cada concesión es auditable | **VALIDATED** | `audit_event`, sin actor |
| 10 | Navegación, página y API coinciden | **VALIDATED** | §7 |
| 11 | Aislamiento entre tenants verde | **VALIDATED** | §9 |
| 12 | La UX visible de RTE08 no cambió | **VALIDATED** | §10; cero archivos de interfaz |
| 13 | Regresión de RTE08 verde | **VALIDATED** | §10 |
| 14 | La instrucción de `bootstrap` queda superseded | **VALIDATED** | §11 |
| 15 | Sin `PARTIAL`/`GAP`/`BLOCKED`/decisión pendiente | **VALIDATED** | §13 |

**Hueco dentro de este delta: ninguno.**

---

## 13. Asuntos restantes

**Dentro del delta: ninguno.**

**Acción operativa — una sola, y es la misma para RTE07 y RTE08:**

```bash
uv run python -m app.db.scripts.align_role_capabilities
```

Hay que ejecutarla **en el entorno desplegado**. Lo de aquí es local, y local no
es compartido. Concede las dos capacidades, dice exactamente qué concedió, y una
segunda ejecución no hace nada.

**Recomendación, no ejecutada por no estar en el alcance:** añadirla al runbook
de despliegue, después de las migraciones. El hueco se abre cada vez que un
checkpoint introduce una capacidad y ya ocurrió tres veces seguidas. No se
conectó al arranque de la aplicación a propósito: conceder autorizaciones sola,
en cada despliegue y sin que nadie lo decida, es un cambio mayor del que esta
instrucción autoriza.

**Deuda preexistente, declarada**: la fragilidad del arnés de §10 y
`BOOTSTRAP_COMPANY_SUBDOMAIN` sin poner en el entorno desplegado. Ninguna de las
dos bloquea este delta; la segunda sigue siendo un riesgo real si alguien
ejecuta `bootstrap` allí.

---

## 14. Estado propuesto

```text
RTE08 ROLE CAPABILITY ALIGNMENT COMPLETE / READY FOR CER FINAL VALIDATION
```

Causa confirmada, mecanismo compartido verificado para esta capacidad, ciclo del
tenant existente probado de punta a punta, idempotencia sobre datos reales,
paridad de las tres capas, Supervisor y aislamiento intactos, UX sin cambios,
regresión verde y la instrucción operativa corregida.

**No se declara `RTE08 CLOSED`**: la certificación del checkpoint es de CER.

---

## 15. Estimación del esfuerzo

| Componente | Líneas |
|---|---|
| `tests/integration/test_rte08_activity_capability_alignment.py` | 261 |
| `tests/e2e/test_rte08_activity_access_browser.py` | 168 |
| Aviso de supersesión en el reporte 001 | 14 |
| **Total** | **≈ 443 / −2** |

| Tarea | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Verificación de catálogo, plantillas y paridad | `DONE` | — | análisis | 0,4 |
| Tests de integración (8) | `DONE` | ~261 LoC | backend | 1,6 |
| Tests de navegador (2) y corrección del localizador | `DONE` | ~168 LoC | UI/navegador | 2,6 |
| Clasificación de la fragilidad del arnés | `DONE` | bisección | diagnóstico | 0,5 |
| Corrección documental | `DONE` | — | documentación | 0,2 |
| Regresión por agrupaciones soportadas | `DONE` | 123 tests | ejecución | 0,8 |
| Reporte 002 | `DONE` | — | documentación | 0,5 |
| **Subtotal ejecutado** | | | | **6,6** |
| Margen de riesgo (+50%, automatización de navegador) | | | | **+3,3** |
| **Total del delta** | | | | **≈ 9,9 h-agente** |

---

## 16. Siguiente paso

Ejecutar el comando en el entorno compartido y validar con la cuenta real de
CER. **No se inicia RTE09, no se reanuda RTE10-A01 y no se modifica RTE07 más
allá de reportar la evidencia compartida de la alineación.**
