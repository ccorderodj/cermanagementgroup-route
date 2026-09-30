# CER Route — Jerarquía, roles y alcance de datos
## Preflight de análisis — no se implementa nada

**Para:** el programador que ejecute el sprint.
**Evidencia:** el repositorio actual, medido. RTE02-A02 y los módulos que
dependen de autorización o de alcance de tenant.
**Estado:** análisis. Ninguna migración, ningún rol, ninguna capacidad, ninguna
pantalla, ninguna API. Nada de RTE03–RTE06 tocado.

---

## 0. Las cuatro cosas que deciden este análisis

**1. La jerarquía no existe en ninguna parte.** No es que esté incompleta:
`grep` de `parent_id|descendant|subordinate|hierarchy` sobre `app/` devuelve
cero resultados de dominio. Hoy hay **dos** alcances de datos y nada más:
tenant (`company_id`, del subdominio) y self (`user_id`, del token, en 71
sitios). Todo lo demás de este documento se construye sobre eso.

**2. Los ciclos se pueden hacer imposibles por construcción, sin comprobación
recursiva.** Si la jerarquía tiene niveles ordenados y se exige que el padre
esté **estrictamente** por encima del hijo, un ciclo no puede existir: seguirlo
exigiría que un nivel fuera menor que sí mismo. Eso elimina el disparador
recursivo que este tipo de modelo suele arrastrar. §D.

**3. El control de A02 se rompe con seis roles, y es el mayor riesgo del
sprint.** Hoy `ROUTE_PRODUCT_ROLES` es un conjunto plano de dos elementos y la
regla es "quien administra desde Route sólo concede roles de Route". Con seis
roles, esa misma regla deja que un **COO conceda CEO**. Hay que convertirla en
una regla **de nivel**, y es un cambio a un control certificado que ya se
reabrió una vez al quitarle una condición. §H.

**4. El editor dinámico de capacidades ya existe, y por eso la respuesta a §F
es "no lo uses para esto".** `rolepermissionsapprovals` es un flujo
maker-checker completo —solicitar no aplica, quien pide no aprueba, sólo
aprueba categoría `management`, una solicitud pendiente por rol, todo acotado a
compañía—. Recomendar "administración de asignaciones" no es evitar construir un
editor: es **no conectar el COO al editor que ya hay**. §F.

---

## A. Current State

### Roles que existen de verdad

| Rol | Categoría | Capacidades | Origen |
|---|---|---|---|
| `owner` | management | `ALL_CAPABILITIES` (`*`) | núcleo |
| `admin` | management | todas menos `roles.delete` | núcleo |
| `manager` | operative | lectura + `users.create/update` | núcleo |
| `viewer` | operative | sólo lectura | núcleo |
| **`supervisor`** | operative | `route.worksession.execute`, `route.standardvalues.read` | **Route** |
| **`route_admin`** | operative | `companies.read`, `regions.read`, `users.read/create/update/delete`, `route.vehicles.read/manage`, `route.standardvalues.read/manage`, `route.records.adjust`, `route.worksession.execute` | **Route** |

`ROUTE_PRODUCT_ROLES = frozenset({"route_admin", "supervisor"})`, con etiquetas
visibles "Administrador" y "Supervisor". El código técnico no se muestra nunca.

### Capacidades

Catálogo único en `app/core/rbac/catalog.py`, y
`tests/test_permission_catalog.py` cruza las dos direcciones: una capacidad que
ningún endpoint exige **hace fallar el test a propósito**. Por eso
`route.live.read`, `route.activity.read`, `route.reports.read`,
`route.reports.export` y `route.fuelreference.manage` **todavía no están
declaradas**: entran con el checkpoint que construya su superficie.

Eso afecta a este sprint: no se pueden declarar capacidades de jerarquía antes
de que existan los endpoints que las exigen.

### Autorización

`require_permissions([...])` resuelve sobre `(user_id, company_id)`:

1. `get_current_membership` comprueba que la identidad global esté activa **y**
   que la pertenencia a esta compañía lo esté;
2. `current_user.is_superuser` → **retorno inmediato**, sin mirar capacidades;
3. si no, se resuelven las capacidades del rol y se comparan.

**No recibe ningún parámetro de alcance.** No sabe *sobre quién* se actúa.

### `/api/route/users` y la relación con los roles del núcleo

El **mismo** `APIRouter` montado dos veces: `/api/users` (contexto núcleo, sin
cambios) y `/api/route/users` (contexto Route, con
`Depends(marcar_contexto_de_route)` que pone un `ContextVar`). No son dos
administraciones de usuarios: son los mismos handlers y el mismo DAO.

### La restricción de asignación de A02, literal

`ensure_assignable_role` acota cuando se cumple **cualquiera** de dos
condiciones:

1. **el contexto es Route** — la petición entró por `/api/route/users`, y eso
   vale para cualquiera, Superadmin incluido (PD-02);
2. **el actor es de Route** — su rol en esta compañía está en
   `ROUTE_PRODUCT_ROLES`, y eso vale por cualquier ruta.

Las dos hacen falta. El repositorio lo dice y lo midió: quitar la segunda
reabrió la escalada al instante, porque un `route_admin` tiene `users.create` y
llamando a `/api/users` volvía a poder crear un `owner` — medido, devolvía 200.

**Hueco declarado y fuera del alcance de A02:** `manager` tiene
`users.create/update` en el núcleo y puede conceder `owner` por el contrato del
núcleo.

### Alcance de tenant

`Depends(get_company_required)` deriva la compañía del **subdominio**. Un
`company_id` en el cuerpo o en la query es un error de diseño (invariante 2). Un
recurso de otra compañía devuelve **404, no 403**.

### Pertenencia

`user_company` con `uq_user_company_user_company` sobre `(user_id, company_id)`,
y **no es parcial**: un usuario tiene **como máximo un rol por compañía**. Eso
simplifica mucho la jerarquía — el nodo de la jerarquía puede ser la pertenencia
misma.

### Componentes reutilizables, verificados

| Componente | Qué aporta a este sprint |
|---|---|
| **Fechado de vigencia de `vehicle_assignment`** | el patrón completo: `EXCLUDE USING gist` sobre `tstzrange(from, to, '[)')`, intervalo estrictamente positivo, resolución `effective_at(moment)`. Es el molde exacto para las relaciones jerárquicas |
| `rolepermissionsapprovals` | flujo maker-checker de cambios de capacidades, ya construido y acotado a compañía |
| `supervisor_profile` | extensión de dominio de quien hace trabajo de campo: `(company_id, user_id)`, soft delete, versionado, único compuesto `(id, company_id)` |
| `record_event` | auditoría append-only por disparador |
| `BusinessEnum` | el enum genera su propio `CHECK` |
| FK compuestas con `company_id` | referenciar otro tenant es imposible por construcción, no por cuidado |
| El patrón `UPDATE ... WHERE estado = 'x'` + `rowcount == 0` | concurrencia sin pisar |

### Un dato medido que evita una decisión de producto

**`Execute` ya funciona sin `supervisor_profile`.** En
`worksessions/service.py` el perfil es opcional: sin él la jornada arranca con
`vehicle_id = null` y el odómetro en `NOT_REQUIRED`. Así que un CEO puede tener
Execute sin ser operativo de campo, y **no hace falta preguntarlo a CER**.

---

## B. Gap Analysis

| Requisito | Existe hoy | Hueco |
|---|---|---|
| Seis niveles de rol | 2 roles de Route | **faltan 4**: CEO, COO, RM, OSM |
| Relación padre/hijo | nada | **toda la relación** |
| Niveles omitidos (COO → OSM sin RM) | nada | depende de lo anterior |
| Vigencia histórica de la relación | el patrón existe en vehículos, no en jerarquía | **la tabla y su invariante** |
| Alcance `descendants` | nada; sólo tenant y self | **el resolver entero** |
| Alcance `self` | sí, en 71 sitios | reutilizable |
| Alcance tenant | sí, del subdominio | reutilizable |
| Administrar asignaciones de rol acotada por nivel | conjunto plano de 2 | **la regla de nivel** |
| Administrar la relación jerárquica | nada | **endpoints + reglas** |
| Administrar catálogos | `route.standardvalues.manage` existe | reutilizable, hay que decidir quién lo recibe |
| Impedir escalada hacia arriba | sí, pero por pertenencia a un conjunto plano | **hay que rehacerlo por nivel** |
| Ver sólo a los subordinados en pantalla | nada | UX + el resolver detrás |

**Lo que no existe y no es obvio que falte:** ninguna capacidad distingue hoy
"administrar usuarios" de "administrar **a quién**". `users.update` es binario.
Toda la diferencia entre lo que un COO y un RM pueden hacer va a vivir en el
alcance, no en la capacidad.

---

## C. Recommended Functional Model

Matriz derivada de los requisitos de CER, sin añadir autoridad.

| Rol | Read | Execute | Manage Users | Manage Hierarchy | Manage Catalogs | Manage Role Assignments | Data Scope |
|---|---|---|---|---|---|---|---|
| **Superadmin (Route)** | todo el tenant | sí | sí | sí | sí | sí, cualquier rol de Route | `TENANT` |
| **CEO** | su organización | sí | dentro de su alcance | sí | sí | roles **por debajo** de CEO | `DESCENDANTS` |
| **COO** | RM, OSM, Supervisores de su estructura | sí | dentro de su alcance | sí | **no** — no lo pide el requisito | roles **por debajo** de COO | `DESCENDANTS` |
| **RM** | OSM y Supervisores de su alcance | sí | dentro de su alcance | **recomendado: sí, acotado** | no | roles **por debajo** de RM | `DESCENDANTS` |
| **OSM** | sus Supervisores | sí | **decisión CER** — §J-1 | no | no | no | `DESCENDANTS` |
| **Supervisor** | su propia operación | sí | no | no | no | no | `SELF` |

Notas, cada una con su razón:

- **El Superadmin de Route es `route_admin` evolucionado**, no un rol nuevo. Ya
  tiene `users.read/create/update/delete`, `route.vehicles.*`,
  `route.standardvalues.*`, `route.records.adjust` y `route.worksession.execute`
  — que es exactamente la lista del §1 del requisito. Lo único que le falta es
  administrar la jerarquía. Introducir un séptimo rol para eso obligaría a
  migrar `role.name` en cada tenant, y A02 lo prohíbe expresamente. **No hay
  razón técnica para un rol nuevo.**
- **El Platform Superadmin del núcleo no se toca.** Sigue con su
  `is_superuser` y su retorno inmediato en `require_permissions`. Este documento
  no propone cambiarlo.
- **COO sin catálogos** porque el §3 del requisito no los pide y §C dice no
  añadir autoridad sin señalarla. Si CER los quiere, es una línea.
- **RM administrando jerarquía acotada** sí es una recomendación mía: el §4 le
  pide administrar OSM y Supervisores, y "administrar un OSM" sin poder decir de
  qué RM cuelga deja la relación a medias. Acotado significa: sólo puede mover
  nodos que ya estén bajo él, y sólo a padres que también estén bajo él.
- **`Read` no es una capacidad nueva por rol.** Lo que cambia entre CEO y RM no
  es *si* pueden leer, es *qué* devuelve la consulta. Eso es alcance.

---

## D. Recommended Hierarchy Model

### La tabla

Una relación, no una columna en `user_company`. Una columna `parent_id` no puede
llevar historial, y el historial es el requisito.

```
route_org_edge
  id, company_id
  child_membership_id     -> user_company(id, company_id)   FK compuesta
  parent_membership_id    -> user_company(id, company_id)   FK compuesta, NULL = raíz
  effective_from, effective_to
```

**Por qué el nodo es la pertenencia y no el usuario:** `user_company` ya tiene
un rol por usuario y compañía, ya lleva `is_active` y `deleted_at`, y la FK
compuesta con `company_id` hace imposible por construcción una arista
entre tenants. Colgar de `user_id` obligaría a repetir la comprobación de tenant
en cada consulta.

**Por qué no extender `supervisor_profile`:** lleva semántica de campo —
vehículo, odómetro, asignación efectiva. Un CEO no es un operativo de campo, y
darle un perfil de supervisor para que quepa en la jerarquía mezclaría dos cosas
que hoy están separadas a propósito.

### El nivel, y lo que regala

Un `level` derivado del rol, no almacenado en la arista:

```
route_admin 0 · CEO 1 · COO 2 · RM 3 · OSM 4 · Supervisor 5
```

Con un invariante: **el padre tiene nivel estrictamente menor que el hijo.**

Eso resuelve tres cosas de una vez:

1. **Los ciclos son imposibles.** Seguir un ciclo exigiría que un nivel fuera
   menor que sí mismo. **No hace falta disparador recursivo ni `ltree`.**
2. **Los niveles omitidos salen gratis.** `COO(2) → OSM(4)` cumple `2 < 4`, así
   que el caso que CER autoriza es válido sin regla especial. Y
   `COO(2) → CEO(1)` es imposible.
3. **"Asignar un superior de menor nivel" queda cerrado** por el mismo
   invariante.

El nivel se deriva del rol de la pertenencia, así que no hay un segundo sitio
donde pueda discrepar. Comprobarlo exige leer los dos roles, que es una consulta
o un disparador; ver §E.

### Vigencia y solapamiento

**Un hijo, un padre vigente en cada instante.** Es el mismo invariante que
`vehicle_assignment`, con el mismo mecanismo:

```sql
EXCLUDE USING gist (
    company_id WITH =,
    child_membership_id WITH =,
    tstzrange(effective_from, effective_to, '[)') WITH &&
)
```

**Y con la trampa que este repositorio ya pagó:** un rango **vacío**
—`effective_to = effective_from`— no solapa con nada, así que `EXCLUDE` no lo
ve. En `vehicle_assignment` eso dejó filas fantasma en el camino concurrente
hasta la migración 0012. Así que desde el principio:

```sql
CHECK (effective_to IS NULL OR effective_to > effective_from)
```

No repitas ese error; está medido y documentado en el reporte de cierre de
RTE06.

### Descendientes

Un CTE recursivo **en un solo sitio**, dentro del resolver de alcance:

```sql
WITH RECURSIVE bajo(id) AS (
    SELECT :raiz
    UNION ALL
    SELECT e.child_membership_id
    FROM route_org_edge e
    JOIN bajo b ON b.id = e.parent_membership_id
    WHERE e.company_id = :c
      AND e.effective_from <= :momento
      AND (e.effective_to IS NULL OR e.effective_to > :momento)
)
SELECT id FROM bajo;
```

`:momento` es el punto entero de la vigencia; ver §J-2.

`ltree` o un camino materializado serían más rápidos y menos simples. Con el
tamaño de una organización de CER —decenas de nodos, no millones— el CTE es
suficiente, y el baseline no justifica más. **No impongas una solución
excesiva.**

### Raíz, self y tenant

- `parent_membership_id IS NULL` = raíz. El Superadmin de Route no necesita
  arista: su alcance es `TENANT`, que no se calcula, se concede.
- `SELF` sigue siendo lo que ya es en 71 sitios.
- `DESCENDANTS` incluye al propio nodo, porque un RM también ve su propia
  operación.

---

## E. Permission / Scope Architecture

### La separación

```
capacidad  → ¿qué puede hacer?        require_permissions([...])   ya existe
alcance    → ¿sobre quién?            resolver nuevo               falta
```

**No codificar la jerarquía dentro de los roles.** Si el alcance viviera en el
rol haría falta un rol por posición en el árbol, y mover a alguien de rama
sería un cambio de rol. El requisito dice explícitamente separarlos.

### El resolver

Una dependencia que devuelve el conjunto de pertenencias sobre las que el actor
puede operar, y **nada más**:

```python
@dataclass(frozen=True)
class DataScope:
    kind: Literal["self", "descendants", "tenant"]
    company_id: int
    membership_ids: frozenset[int] | None   # None = tenant entero
    as_of: datetime

def require_scope(...) -> Callable   # dependencia FastAPI
```

Tres propiedades que lo hacen usable sin duplicar lógica:

1. **Se resuelve en el servidor, del token y del subdominio.** El cliente nunca
   envía un alcance. Eso es explícito en el requisito y ya es invariante del
   repositorio.
2. **Devuelve ids, no un filtro.** Cada módulo decide cómo usarlo: un `IN`, un
   `JOIN` o una subconsulta. Devolver un objeto de filtro ataría el resolver al
   ORM de cada módulo.
3. **`kind = "tenant"` devuelve `None` y no una lista.** Materializar todas las
   pertenencias de un tenant para un Superadmin sería trabajo inútil en cada
   petición, y un `None` explícito obliga a quien lo consume a tratar el caso
   en vez de olvidarlo.

### Cómo lo consumen los módulos futuros

El patrón que deben seguir Today/Live, Activity y Reports:

```python
async def listar(
    scope: DataScope = Depends(require_scope("route.live.read")),
):
    filas = await Dao.query(company_id=scope.company_id,
                            membership_ids=scope.membership_ids)
```

El DAO recibe `membership_ids=None` para tenant entero y un conjunto para el
resto. **Un solo sitio sabe qué es un descendiente**, igual que hoy un solo
sitio sabe qué es una capacidad.

**Riesgo que hay que cerrar con una red de test**, y conviene escribirla en este
sprint aunque los módulos no existan: un endpoint que reciba `DataScope` y
**no** lo pase al DAO compila, pasa los tests de autorización y devuelve datos
de todo el tenant. Es el mismo tipo de hueco que
`tests/test_public_surface.py` cierra para la superficie pública: una lista
cerrada de endpoints con alcance, que falle cuando alguien añada uno sin
declararlo.

---

## F. Role Administration Recommendation

### Qué significa "el COO administra roles/permisos"

Dos lecturas posibles, y sólo una es lo que el requisito pide:

**A. Administración de asignaciones.** Asignar CEO/COO/RM/OSM/Supervisor,
cambiar el rol de alguien, asignarle un superior, reasignar la estructura,
activar/desactivar, consultar el historial.

**B. Administración del contenido del rol.** Añadir o quitar capacidades al rol
COO, cambiar qué significa RM, crear roles arbitrarios.

### Recomendación: **A**, y B **no** se conecta al COO

**A satisface el requisito completo.** El §3 del requisito pide administrar RM,
OSM, Supervisores y *las relaciones entre ellos*, y "asignaciones de
roles/permisos dentro del alcance autorizado". Todo eso es A.

**Y B ya existe**, que es el dato que decide: `rolepermissionsapprovals` es un
flujo maker-checker completo —solicitar no aplica el cambio, quien pide no
aprueba, sólo aprueba quien es categoría `management` o administrador de
plataforma, una solicitud pendiente por rol, todo acotado a compañía—.

Así que la recomendación no es "no construyas un editor". Es: **no conectes el
COO al editor que ya hay.** Razones:

1. **Rompería el modelo de aprobación.** Ese flujo exige que apruebe categoría
   `management`. Los roles nuevos son `operative`. Conectar el COO obligaría o a
   hacerlo `management` —lo que le daría autoridad de seguridad del tenant— o a
   inventar un segundo modelo de aprobación.
2. **Convertiría el alcance en algo que se puede editar.** Si el COO puede
   cambiar qué capacidades tiene el rol COO, puede darse `roles.update`, y desde
   ahí todo. La escalada dejaría de depender de una regla de nivel y pasaría a
   depender de que nadie se equivoque al editar.
3. **El requisito no lo pide.** Pide administrar *asignaciones dentro del
   alcance autorizado*. "Dentro del alcance autorizado" es precisamente la
   frase que A implementa y B disuelve.

**Si CER quisiera B más adelante**, el camino existente es el correcto: una
solicitud del COO que aprueba un `management`. Eso no necesita código nuevo,
sólo conceder `rolepermissions.update` — y es reversible.

### La regla de asignación, concretamente

Sustituir la comprobación de pertenencia a un conjunto plano por una de nivel:

```
un actor puede conceder el rol R  ⟺  level(R) > level(rol del actor)
                                  ∧  R ∈ roles de Route
                                  ∧  el objetivo está en su alcance
```

Las tres condiciones. La primera cierra la escalada hacia arriba y lateral —un
RM no puede conceder RM, porque `3 > 3` es falso—. La segunda conserva lo que
A02 ya garantiza: desde Route no se conceden roles del núcleo. La tercera es
nueva y es la que impide administrar a alguien de otra rama.

---

## G. UX Impact

Sin diseñar pantallas. Qué tiene que cambiar y por qué:

| Superficie | Cambio | Por qué |
|---|---|---|
| **Users (lista)** | filtrada por el alcance del actor | un RM que ve todo el tenant es una fuga, aunque no pueda editarlo |
| **Selector de rol** | sólo roles estrictamente por debajo del actor | hoy ofrece dos opciones fijas; pasa a depender del actor. **Sigue siendo experiencia**: la puerta está en el servidor |
| **Alta de usuario** | pasa a exigir **superior** | un usuario sin padre no tiene sitio en la organización, salvo la raíz |
| **Administración de jerarquía** | superficie nueva: ver el árbol, mover un nodo, cerrar y abrir una relación | es el requisito de CEO/COO/RM |
| **Cambio de relación** | fecha de efecto explícita, no "ahora" implícito | sin ella, mover a alguien reescribiría el pasado; ver §J-2 |
| **Historial** | lectura de las aristas cerradas de una persona | el requisito pide consultar historial, y es lo que hace auditable un reporte de junio |
| **Visibilidad por rol** | el menú lateral ya filtra por capacidad; ahora además hay contenido que depende del alcance | el filtrado de menú existe (`navigation.ts` con `requiredPermission`) |

Lo que **no** cambia: el workbench de RTE05, el flujo de Change Plan, la captura
de ubicación. Son de `Execute` y `Execute` es `SELF`.

---

## H. Security Analysis

### Escalada de privilegio

| Vector | Cómo se cierra |
|---|---|
| COO se hace CEO | regla de nivel: `level(CEO)=1 > level(COO)=2` es falso |
| COO se hace Superadmin de Route | id. y además `route_admin` es nivel 0 |
| RM administra otro RM | `3 > 3` es falso |
| Asignar un superior de menor nivel | invariante padre/hijo de la arista |
| Ciclos | imposibles por el orden de niveles — §D |
| Concederse a uno mismo un rol superior | la regla de nivel se aplica también cuando el objetivo es el actor. **Escríbelo como test explícito**; es el caso que se olvida |
| Conceder roles del núcleo desde Route | ya cerrado por A02, y **hay que conservar las dos condiciones** |

### **El riesgo de rehacer el control de A02**

Es el punto más delicado del sprint y merece decirse solo.

El control actual funciona porque `ROUTE_PRODUCT_ROLES` es un conjunto **plano**:
"sólo roles de Route" es suficiente cuando hay dos y ninguno manda sobre el
otro. Con seis roles ordenados, la misma frase permite que un COO conceda CEO.

El repositorio ya registra que **quitarle una condición a este control reabrió
la escalada al instante**, medido contra la API con un 200. Así que:

1. las dos condiciones de A02 —contexto de Route **y** actor de Route— se
   conservan tal cual, y la de nivel se **añade**, no sustituye;
2. `ROUTE_PRODUCT_ROLES` pasa de conjunto a mapa ordenado
   `{rol: nivel}`, y todo lo que hoy pregunta "¿está en el conjunto?" sigue
   funcionando con `in`;
3. los tests de A02 se conservan **sin tocar** y se añaden los de nivel. Si
   alguno de los viejos hay que cambiarlo, es señal de que el control se está
   aflojando.

### Aislamiento de tenant

FK compuestas con `company_id` en las dos puntas de la arista → una arista
entre tenants es imposible por construcción. El resolver deriva `company_id`
del subdominio, nunca del cliente. El CTE recursivo filtra por `company_id` en
cada nivel, no sólo en la raíz — **eso es fácil de olvidar y hay que probarlo**:
una arista con `company_id` distinto no debe poder aparecer en el descenso.

### Administración hacia arriba y hacia abajo

Hacia arriba: cerrado por nivel. Hacia abajo: acotado por alcance. **Lateral**
es el que se olvida: dos COO del mismo CEO no deben poder administrarse entre
sí, y eso no lo cierra el nivel —son iguales— sino el alcance: un COO no está
bajo otro COO.

### Bypass directo de API

`/api/users` del núcleo sigue existiendo y `route_admin` tiene `users.*`. Lo
cierra hoy la segunda condición de A02. Con seis roles hay **más actores** en esa
situación, así que la comprobación de que el actor es de Route tiene que
reconocer los seis. Un CEO que no esté en el mapa de niveles quedaría fuera del
control y podría usar `/api/users` para conceder `owner`.

### Solapamiento de vigencia

`EXCLUDE` + intervalo estrictamente positivo — §D. Y el caso concurrente que
`vehicle_assignment` sufrió: dos cambios de padre en el mismo instante.

### Auditoría

`record_event` para: crear arista, cerrar arista, cambiar rol, activar y
desactivar. Con `changes` que diga padre anterior → padre nuevo y rol anterior →
rol nuevo. Sin eso, "¿quién movió a este supervisor en julio?" no tiene
respuesta.

### Mínimo privilegio

Dos observaciones del baseline:

- **OSM no debe recibir `Manage` si el requisito no lo pide.** §J-1.
- **El retorno inmediato de `is_superuser`** en `require_permissions` significa
  que un Superadmin de plataforma pasa por encima de todo el alcance. Para las
  pantallas de administración es correcto; para las operativas ya se corrigió en
  RTE05 con un guard propio (`exige_ejecucion_de_ruta`). **Si las pantallas de
  jerarquía se montan bajo `/admin`, heredan el bypass**, y hay que decidir si
  eso es lo que se quiere. No es un defecto: es una decisión que conviene tomar
  a la vista.

---

## I. Compatibility / Regression Impact

| Entrega | Impacto | Por qué |
|---|---|---|
| **RTE02 Users / Roles** | **Adaptation required** | es el sujeto del cambio: cuatro roles nuevos, la regla de nivel, la jerarquía, el alcance en la lista de usuarios |
| **RTE02-A02 controles** | **Adaptation required** | §H. Se **añade** la regla de nivel; no se sustituyen las dos condiciones |
| **RTE03 Work Sessions** | **Regression only** | `Execute` es `SELF` y ya filtra por `user_id` del token. Nada que adaptar; hay que **volver a correrlo** porque los roles nuevos tienen `execute` |
| **RTE04 Trips / Odometer** | **Regression only** | id. Y un dato medido: `Execute` funciona sin `supervisor_profile`, así que un CEO puede abrir jornada sin vehículo y el odómetro queda `NOT_REQUIRED` — comportamiento ya existente |
| **RTE05 Activities** | **Regression only** | id. El guard `/route` exige `route.worksession.execute`, que los seis roles tendrán |
| **RTE06 Location / Mileage** | **Regression only** | la correlación es por fila de dominio y la lectura ya filtra por la jornada del propio usuario |
| **Today/Live (futuro)** | **depende de este sprint** | es el primer consumidor real de `DESCENDANTS`. Si el resolver no está, nace con alcance de tenant y hay que rehacerlo |
| **Activity Explorer (futuro)** | id. | id. |
| **Reports (futuro)** | id., y **es el que fuerza la vigencia histórica** | §J-2 |

**Ninguna entrega necesita rediseño funcional.** El motivo es concreto: todo lo
que RTE03–RTE06 construyó es `Execute`, y `Execute` es `SELF`. La jerarquía
añade alcances de lectura y administración por encima, sin tocar la ejecución.

**La excepción a vigilar:** el guard de las páginas de Route
(`exige_ejecucion_de_ruta`) es más estricto que el del núcleo a propósito — no
hace el bypass de superusuario. Los seis roles tienen que pasarlo, y eso es una
línea, pero si se olvida, un CEO no puede abrir su propia jornada.

---

## J. Decisions Required from CER

Sólo lo que de verdad necesita al Product Owner. Las decisiones técnicas
—tabla, resolver, CTE, `EXCLUDE`— están tomadas arriba.

### J-1 · ¿El OSM administra a sus Supervisores, o sólo los ve?

**Issue.** El §5 del requisito le da "visibilidad" y `Execute`, y dice
expresamente no inventarle `Manage`. Pero el §4 le da al RM administrar
Supervisores, así que un Supervisor puede ser administrado por su RM sin que su
OSM directo pueda hacerlo. Eso es coherente, y también puede no ser lo que se
quiere en la operación diaria.

**Options.**
- **(a) Sólo ver.** OSM lee su equipo, no lo administra.
- **(b) Ver y administrar sus Supervisores.** Puede cambiar rol y activar o
  desactivar dentro de su alcance.

**Impact.** (a) no cuesta nada: es el modelo tal como está descrito. (b) añade
un nivel más de administración y hay que decidir si el OSM puede además mover un
Supervisor a otro OSM, que es una operación entre ramas.

**Recommendation. (a).** Es lo que el requisito dice, no añade autoridad y (b)
se puede conceder después sin migración: es la regla de nivel, que ya estará
escrita. Empezar por (b) y retirarlo después sí sería un cambio visible.

**Decision required.** Sí.

---

### J-2 · ¿El alcance sobre datos históricos sigue la jerarquía de entonces o la de hoy?

**Issue.** Un Supervisor estuvo bajo el OSM A de enero a junio y bajo el OSM B
desde julio. Cuando el OSM A pide el reporte de junio, ¿lo ve?

Es **la** decisión de este sprint, y no es técnica: cambia qué números ve cada
persona.

**Options.**
- **(a) Jerarquía de entonces** (`as_of` = la fecha del dato). El OSM A ve junio
  para siempre; el OSM B no ve junio.
- **(b) Jerarquía de hoy** (`as_of` = ahora). El OSM B ve todo el historial del
  supervisor que tiene ahora; el OSM A deja de ver junio.

**Impact.** (a) hace que un reporte histórico sea reproducible: el total de
junio del OSM A es el mismo dentro de un año. (b) hace que "mi equipo" signifique
siempre el equipo actual, que es más intuitivo en una pantalla operativa, pero
un reporte deja de ser estable — el mismo informe da distinto según cuándo se
pida, sin que nada haya cambiado salvo la estructura.

**Recommendation. (a) para reportes e historial, (b) para las pantallas
operativas**, y el resolver toma `as_of` como parámetro para poder hacer las dos
sin duplicar lógica. La recomendación de CER de preservar historial apunta a
(a), y mezclarlas sin decidirlo produciría exactamente la inconsistencia que la
vigencia pretende evitar.

**Decision required.** Sí. Y si sólo se puede decidir una, que sea (a): un
reporte que cambia solo es un problema mayor que una pantalla que enseña de
menos.

---

### J-3 · Combinaciones de jerarquía no declaradas

**Issue.** CER confirmó `COO → RM → OSM → Supervisor` y `COO → OSM`. No dijo
nada de `CEO → RM` directo, `CEO → Supervisor`, `RM → Supervisor` sin OSM —este
último sí aparece en el diagrama— ni de `COO → Supervisor`.

El invariante de nivel las permitiría **todas**, porque sólo exige que el padre
esté por encima. Eso puede ser deseable o demasiado.

**Options.**
- **(a) Cualquier salto hacia abajo.** El invariante de nivel a secas.
- **(b) Sólo las combinaciones declaradas**, con una tabla de parejas
  permitidas.

**Impact.** (a) es más simple, más flexible y no necesita mantenimiento. (b)
es más estricto y obliga a una decisión de CER cada vez que la organización
cambie de forma.

**Recommendation. (a).** El requisito dice "la jerarquía admite niveles omitidos
donde CER lo ha definido", y los dos casos definidos son saltos. Una tabla de
parejas para permitir dos casos y prohibir tres que nadie ha pedido es
complejidad sin beneficio, y el invariante de nivel ya impide lo peligroso
—subir—. **Pero la pregunta es de CER**, porque decide qué estructuras se pueden
representar.

**Decision required.** Sí.

---

### J-4 · ¿Una persona puede tener dos posiciones?

**Issue.** `uq_user_company_user_company` es **completo**: un usuario tiene un
rol por compañía, y por tanto una posición en el árbol. Así que "María es RM de
la región norte y OSM interino de un equipo" no se puede representar.

**Options.**
- **(a) Una posición por persona.** El modelo actual, sin cambios.
- **(b) Varias.** Habría que hacer parcial ese único, que es un cambio a un
  invariante del **núcleo** con impacto más allá de Route.

**Impact.** (a) no cuesta nada. (b) toca el modelo de pertenencia del núcleo,
afecta a `require_permissions` —que hoy resuelve un rol— y abre la pregunta de
qué capacidades tiene alguien con dos roles.

**Recommendation. (a)**, y si hace falta el caso, cubrirlo con una arista
adicional de **alcance** sin un segundo rol: María sigue siendo RM y se le añade
un equipo. Eso cabe en el modelo propuesto y no toca el núcleo.

**Decision required.** Sólo si CER sabe que el caso existe. Si no, se decide (a)
por omisión y se revisa cuando aparezca.

---

## K. Proposed Sprint Structure

La secuencia preferida de CER funciona, con un cambio que el repositorio
justifica: **el alcance de datos va antes de la UX de administración**, porque
la lista de usuarios filtrada es la primera pantalla que lo necesita y
construirla sin resolver la devolvería entera.

| CP | Nombre | Contenido | Por qué aquí |
|---|---|---|---|
| **CP0** | Baseline y decisiones | este análisis + las cuatro decisiones de §J resueltas | sin J-2 no se puede escribir el resolver |
| **CP1** | Roles y niveles | los cuatro roles nuevos, `ROUTE_PRODUCT_ROLES` → mapa ordenado, la regla de nivel en `ensure_assignable_role`, tests de escalada | es el cambio al control certificado; solo, con su propia regresión |
| **CP2** | Jerarquía | `route_org_edge`, invariante de nivel, `EXCLUDE` con intervalo positivo, endpoints de lectura y cambio, auditoría, historial | necesita CP1 para conocer los niveles |
| **CP3** | Alcance de datos | `DataScope`, `require_scope`, el CTE, `as_of`, la red de test de endpoints con alcance | necesita CP2 |
| **CP4** | UX de administración | lista filtrada, selector por nivel, árbol, cambio de relación con fecha, historial | necesita CP3 |
| **CP5** | Seguridad y regresión | matriz de escalada completa, aislamiento bajo carga, RTE02–RTE06 por lotes, navegador | al final, sobre todo montado |
| **CP6** | Cierre | reporte | |

**CP1 va solo a propósito.** Toca el control que ya se reabrió una vez al
quitarle una condición. Mezclarlo con la tabla de jerarquía haría que una
regresión de escalada fuera difícil de atribuir.

---

## L. Effort Estimate

En **horas-agente**. Los coeficientes son los del protocolo del proyecto:
backend/dominio/migraciones 150–200 LoC/h, integración 80–100, UI/navegador
50–70.

| CP | Alcance | Mín | Probable | Alto | Incertidumbre principal | Depende de |
|---|---|---|---|---|---|---|
| **CP0** | decisiones + plan de migración | 1,0 | **1,5** | 2,0 | que J-2 se responda | CER |
| **CP1** | 4 roles, mapa de niveles, regla de nivel, tests de escalada | 4,0 | **6,0** | 9,0 | **cuántos tests de A02 hay que tocar.** Si hay que cambiar alguno, el control se está aflojando y hay que parar a pensar | CP0 |
| **CP2** | tabla, invariantes, migración, endpoints, auditoría, historial | 7,0 | **10,0** | 15,0 | el invariante de nivel: comprobarlo en disparador o en servicio. Disparador es más seguro y más lento de escribir | CP1 |
| **CP3** | resolver, CTE, `as_of`, red de test | 5,0 | **7,0** | 11,0 | si J-2 pide las dos semánticas, el resolver lleva parámetro y todos sus tests se duplican | CP2 |
| **CP4** | lista filtrada, selector, árbol, relación con fecha, historial | 9,0 | **14,0** | 22,0 | **la pantalla del árbol.** Es UI nueva sin precedente en el repositorio; el resto reutiliza `DataTable` |
| **CP5** | matriz de escalada, aislamiento, regresión completa, navegador | 6,0 | **9,0** | 14,0 | lotes de navegador y el churn de conexiones del arnés, ya conocido | CP4 |
| **CP6** | reporte | 1,5 | **2,0** | 3,0 | | CP5 |
| | **Subtotal** | **33,5** | **49,5** | **76,0** | | |

Por tipo de trabajo, sobre la probable:

| Tipo | Horas |
|---|---|
| Análisis y decisiones | 1,5 |
| Backend y dominio | 16,0 |
| Datos y migraciones | 5,0 |
| Frontend | 14,0 |
| Tests | 8,0 |
| Regresión | 3,0 |
| Cierre y reporte | 2,0 |

Con el **margen de riesgo declarado**: deterministas +10 % sobre CP1–CP3 y CP6,
UI/navegador +50 % sobre CP4 y CP5.

```
probable con margen  ≈  49,5 + 10% (24,5)  + 50% (23,0)  ≈  63,4 horas-agente
```

**Supuestos que lo bajan:**
- J-1 se decide (a) — sin `Manage` para OSM: −2 h
- J-2 se decide sólo (a) — una sola semántica en el resolver: −3 h
- J-3 se decide (a) — invariante de nivel a secas, sin tabla de parejas: −2 h
- el árbol se resuelve con una lista indentada en vez de un componente de árbol:
  −4 h

**Supuestos que lo suben:**
- J-4 se decide (b) — toca el único de `user_company`, que es del **núcleo**:
  +8 h y cambia la clasificación de RTE02 de adaptación a rediseño parcial
- hay que tocar tests de A02: +3 h y una revisión de seguridad
- el invariante de nivel se implementa con disparador recursivo por si acaso:
  +3 h, y es evitable — §D explica por qué no hace falta
- J-2 pide las dos semánticas: +3 h

**No se infla por Git ni DevOps.** Rama, commits, MR y despliegue no están en
estas cifras.

---

## M. Recommendation to Programmer

### 1. ¿Antes de RTE07? **Sí, y es la recomendación más firme de este documento.**

RTE07 es Today/Live, y Today/Live es **el primer consumidor real de
`DESCENDANTS`**. Construirlo sin el resolver significa que nace con alcance de
tenant: un RM viendo la jornada de todos. Después habría que volver a entrar en
cada endpoint y en cada consulta a añadir el filtro, con la regresión de RTE07
ya certificada encima.

El coste de hacerlo después no es la diferencia de esfuerzo: es que un alcance
que se añade tarde se olvida en algún sitio, y ese sitio devuelve datos de todo
el tenant sin que ningún test lo note. Es exactamente la clase de hueco que
`test_public_surface.py` existe para cerrar en la superficie pública, y aquí no
habría red equivalente hasta que se escriba.

### 2. Tamaño y riesgo reales

**Tamaño medio, riesgo concentrado.** ~63 horas-agente con margen, repartidas en
siete checkpoints, y RTE03–RTE06 sólo necesitan volver a correr.

El riesgo **no** está donde parece. La tabla de jerarquía, el CTE y el resolver
son trabajo conocido con patrones que ya existen en este repositorio. El riesgo
está en **CP1**: rehacer la regla de asignación de roles de A02. Ese control ya
se reabrió una vez al quitarle una condición, y se midió con un 200 contra la
API. Por eso CP1 va solo, por eso los tests de A02 no se tocan, y por eso si
alguno hay que cambiarlo la respuesta correcta es parar, no adaptarlo.

Segundo foco: el CTE recursivo tiene que filtrar por `company_id` **en cada
nivel**, no sólo en la raíz. Es una línea y es fácil de omitir.

### 3. Arquitectura recomendada, en una frase

**RBAC con alcance jerárquico de datos**, no jerarquía dentro de los roles:
capacidades donde ya están, una tabla de aristas con vigencia sobre
`user_company`, niveles derivados del rol que hacen los ciclos imposibles por
construcción, y **un solo** resolver de alcance que todos los módulos consumen.

### 4. Secuencia sugerida

```
CP0 decisiones  →  CP1 roles y niveles  →  CP2 jerarquía
              →  CP3 alcance  →  CP4 UX  →  CP5 seguridad  →  CP6 cierre
```

Con el cambio respecto a la preferencia de CER: **el alcance antes de la UX**,
porque la primera pantalla que lo necesita es la lista de usuarios filtrada, y
construirla sin resolver la devolvería entera.

Y dos cosas que conviene escribir en CP3 aunque los módulos que las usen no
existan todavía: la **red de test de endpoints con alcance** —para que un
endpoint que recibe `DataScope` y no lo pasa al DAO haga fallar la suite— y el
parámetro `as_of`, para no tener que volver a entrar en el resolver cuando
lleguen los reportes.

# STOP

No se ha implementado nada. Las cuatro decisiones de §J son de CER; el resto
está decidido aquí.
