# AGENTS.md

Reglas para trabajar en este repositorio. Complementa `docs/ARCHITECTURE.md`
(que explica *cómo está armado*), `docs/DEVELOPMENT_WORKFLOW.md` (cómo se trabaja),
`_cer_delivery/recomendaciones_eficientes_y_ejecutables.md` (cómo debe responder,
recomendar y decidir el agente) y
`_cer_delivery/progreso_y_reporte_de_ejecucion.md` (cómo debe reportar mientras
ejecuta); esto dice *qué hacer y qué no*.

---

## Contexto

Base **multi-tenant** para aplicaciones CER construidas como monolitos modulares.
FastAPI + PostgreSQL detrás; React + TypeScript delante, servido por Jinja. Cada
aplicación posee un dominio acotado y se integra con las demás por REST
versionado (`/api/v1`) y webhooks firmados (ver `docs/INTEGRATION_GUIDE.md`).

Patrón de render: **ruta FastAPI → plantilla Jinja → el bundle de React elige la
página por el nombre de la ruta**. No hay router de frontend.

Archivos que conviene tener a mano:

```
app/main.py                                        composicion: raiz, /api, /api/v1, paginas
app/config.py                                      Settings, identidad APP_* y validacion de arranque
app/core/identity.py                               identidad del proyecto para plantillas y app_data
app/core/rbac/catalog.py                           catalogo de capacidades (FUENTE UNICA)
app/core/dao/base.py                               BaseDAO: query() + paginate()
app/core/dao/concurrency.py                        ensure_version(): 409 en vez de pisar
app/core/enums.py                                  BusinessEnum: el enum genera su CHECK
app/core/audit/                                    audit_event append-only + record_event()
app/core/db/session.py                             transaction()
app/core/integration/                              /api/v1, webhooks, firma, idempotencia
app/core/storage/                                  archivos y frontera del escaner
app/routers_api/api.py                             registro privado
app/routers_api_public/api.py                      lista blanca publica
app/routers_pages/                                 rutas de pagina
app/templates/base.html                            esqueleto + #rootReact
app/components/react/index.tsx                     entrada del bundle
.../maincontent/ui/maincontent.ts                  enum ComponentRoot
.../maincontent/config/mainContentConfig.tsx       mapa clave -> componente
.../maincontent/config/navigation.ts               menus (lateral de negocio, usuario de administracion)
tests/test_page_wiring.py                          red del cableado de paginas
tests/test_navigation_wiring.py                    red de enlaces y menus
tests/test_permission_catalog.py                   red del catalogo de capacidades
tests/test_public_surface.py                       red de lo que se sirve sin sesion
```

---

## Invariantes

Cosas que **no se rompen**. Cada una tiene detrás un incidente real del proyecto
de origen (CER Staffing), del que esta base se extrajo.

### 1. El router público declara endpoints, nunca routers

```python
# MAL — publica todo lo que el modulo tenga hoy y todo lo que se le anada manana
api_router_public.include_router(router_users)

# BIEN — cada endpoint publico es una decision escrita
api_router_public.include_router(public_auth_router)   # login, logout, reset
```

Incluir routers de dominio enteros publicó sin autenticación `register`,
`change-password`, el perfil y tres endpoints que devolvían datos del tenant. El
problema no fue la lista: fue que **crecía sola**.

`tests/test_public_surface.py` mantiene la lista cerrada. Añadir un endpoint
público obliga a editar ese test, que es cuando alguien tiene que justificarlo.

### 2. El tenant sale del subdominio, jamás del cliente

Todo endpoint de compañía usa `Depends(get_company_required)` y pasa
`company_id` al DAO. Un `company_id` que llegue en el cuerpo o en la query es un
error de diseño.

### 3. `Users.is_superuser` no es un permiso de tenant

Es privilegio de **plataforma**. No está en el catálogo, no se acepta en ningún
schema de entrada de las APIs de tenant y no aparece como campo editable. Que
estuviera en el formulario de usuarios permitía que cualquiera con `users.create`
se fabricara acceso a todos los tenants.

### 4. Las capacidades se declaran en un solo sitio

`app/core/rbac/catalog.py`. Añadir un endpoint con permiso nuevo son dos pasos:
declararla ahí y usarla en `require_permissions([...])`.

`tests/test_permission_catalog.py` cruza las dos direcciones. Ya divergieron una
vez: `regions.update` estaba en el código y nunca se sembró, así que dos
endpoints devolvían 403 a todo el mundo y nadie lo notó.

### 5. La misma cadena, en cuatro sitios

Nombre de la ruta FastAPI = valor de `ComponentRoot` = clave de `RootComponents`
= nombre de la carpeta en `pages/`. Si divergen, **la página sale en blanco sin
lanzar ningún error**.

`tests/test_page_wiring.py` lo comprueba. Ejecutarlo tras añadir una página.

### 6. La integridad la garantiza la base

Una comprobación en Python protege mientras nadie se olvide de llamarla. Una
restricción de la base protege siempre. Al modelar algo que no puede pasar, se
escribe la constraint **y** el test que comprueba que la base la rechaza.

### 7. Sin React Router

El patrón es server-route + page-key. Introducir un router de frontend rompe la
mitad de la arquitectura.

### 8. Los permisos del frontend son experiencia de usuario

La cookie `user_data` es legible y editable desde el navegador. Ocultar un botón
mejora la experiencia; **no** es un control. La puerta está en el backend.

### 9. Un dato canónico tiene un solo dueño

Cada aplicación y cada módulo poseen su dominio. Otro módulo o aplicación que
necesite ese dato lo **referencia** (id) o lo **consume** (API o evento); no lo
copia a una tabla propia. Dos persistencias del mismo hecho acaban diciendo
cosas distintas.

### 10. `/api/v1` es un contrato; `/api/<módulo>` no

La API interna evoluciona con la interfaz. La versionada la consumen otras
aplicaciones: un cambio incompatible es `/api/v2`, nunca una edición de `v1`.
Lo que se sirve sin sesión bajo `/v1` está enumerado en
`tests/test_public_surface.py`.

---

## Reglas generales

1. Cambios mínimos y coherentes con lo que ya hay.
2. Al tocar un archivo, no dejar código muerto ni comentado dentro.
3. Si el comportamiento cambia, actualizar la documentación en el mismo cambio.
4. Nada de literales mágicos para estados de negocio: `StrEnum` en Python y
   `CHECK` en la base.
5. Las operaciones que tocan más de una tabla van dentro de
   `async with transaction():`.
6. Los helpers genéricos del frontend van a
   `app/components/react/shared/lib/utils/utils.ts`. Los ficheros `util.ts` por
   feature quedan solo para lógica de ese dominio.
7. La identidad del proyecto (nombre, marca, logo, entorno, página de inicio)
   sale de `APP_*` en `app/config.py`, nunca de literales en plantillas o
   componentes.
8. Para contenido configurable por la compañía (nombre, dirección, colores,
   logo) **no** se ponen valores de reserva de negocio: vacío por defecto.

---

## Backend

### Estructura de un módulo

```
app/routers_api/<dominio>/
    router.py         handlers finos: request -> schema -> DAO -> response
    schemas.py        Pydantic de entrada y salida
    models.py         modelos SQLAlchemy
    dao.py            acceso a datos
    dependencies.py   solo si hace falta
```

### Reglas

1. Contratos explícitos: schema de entrada y de salida por endpoint.
2. Handlers finos. La lógica de datos al DAO; las reglas de negocio a un
   `service.py` cuando crecen (ver `rolepermissionsapprovals`).
3. **Alcance de compañía obligatorio.** `Depends(get_company_required)` y
   `company_id` en el DAO.
4. **Autorización explícita.** `Depends(require_permissions(["modulo.accion"]))`.
   Si es una operación de plataforma, `Depends(require_platform_admin)`.
5. **Paginación**: se implementa `query()` en el DAO y se usa `paginate()`. No se
   escriben `get_total` ni `calculate_offset`: estaban duplicados en siete de
   ocho módulos.
6. Registro: privados en `app/routers_api/api.py`; públicos, uno a uno, en
   `app/routers_api_public/api.py`.
7. Errores con códigos estables: 401 sin sesión, 403 sin permiso, 404 para lo que
   no existe **o pertenece a otro tenant**, 409 para conflictos, 422 para
   validación.
8. Un recurso de otra compañía devuelve **404, no 403**: no se confirma que exista.

### Comprobación antes de dar algo por hecho

```bash
uv run python -c "import app.main"
uv run pytest tests/test_permission_catalog.py tests/test_public_surface.py
```

---

## Frontend

### Reglas

1. Componentes enfocados; la configuración estática separada del render.
2. Reutilizar las primitivas de `shared/ui/shadcn/new-york`.
3. **Los paneles no llaman endpoints.** Consumen selectores y despachan thunks:
   carga inicial, filtros, cambio de página y de tamaño.
4. **Validar las respuestas con Zod.** El esquema vive junto a la entidad y de él
   sale el tipo con `z.infer`:

   ```ts
   export const roleSchema = z.object({ id: z.number(), name: z.string() });
   export type Role = z.infer<typeof roleSchema>;

   return parseApi(z.array(roleSchema), response.data, 'fetchRoles');
   ```

   No se usa `api.get<T>()` como si fuera una validación: no comprueba nada.
5. **Un solo cliente HTTP**: Axios, desde `shared/api`. No añadir RTK Query ni
   ningún otro.
6. `model/types` contiene **solo** `index.ts`.
7. Los tres thunks de paginación (`fetch<E>Pagination`,
   `fetchSetPageIndex<E>Pagination`, `fetch<E>PaginationPageSize`) van en el
   **mismo archivo**.
8. La traducción base-0 ↔ base-1 se hace con `toServerPageParams`, no a mano.
9. **Tablas**: `DataTable` + `DataTablePagination` de `features/Common`. No se
   copian: había una segunda implementación completa con siete archivos muertos.
10. Acciones de fila con el patrón `meta` de TanStack
    (`table.options.meta?.renderRowActions?.(...)`).
11. En una carpeta de tabla nueva, solo los archivos que se usan.
12. **Usar los tokens de color**, no `slate-*` ni hexadecimales: el sidebar con
    colores fijos no respondía a la marca del tenant.
13. **No hay modo oscuro.** No añadir utilidades `dark:` ni un toggle.

### Comprobación

```bash
cd app
npm run check     # typecheck + lint
```

`tsc` pasa en 0 errores y debe seguir así.

---

## Añadir una página

1. Ruta en `app/routers_pages/.../router.py` con `name="AlgoPage"` **y** su
   `dependencies=[Depends(require_page_permissions([...]))]`.
2. Cadena de inclusión: router de feature → router padre → `page.py`.
3. Plantilla en `app/templates/...`:
   ```html
   {% extends "base.html" %}
   {% block content %}
     <div id="rc-currentPage" data-current-page="{{ url_name }}"></div>
   {% endblock %}
   ```
   **Con comillas.** Un `name=` con espacios rompería el HTML en silencio.
4. Página React en `pages/<AlgoPage>/`, exportada en su `index.ts`.
5. Clave en `maincontent.ts`.
6. Entrada en `mainContentConfig.tsx`.
7. Ítem de menú en `navigation.ts` con su `requiredPermission`, si procede
   (trabajo de negocio en `businessNavigation`; administración en
   `administrationNavigation`).
8. `uv run pytest tests/test_page_wiring.py tests/test_navigation_wiring.py`.

---

## Añadir una capacidad

1. Declararla en `app/core/rbac/catalog.py`.
2. Usarla en `require_permissions([...])` o `require_page_permissions([...])`.
3. Decidir qué roles por defecto la reciben (`DEFAULT_ROLES`).
4. `uv run python -m app.db.scripts.bootstrap` para sembrarla.
5. `uv run pytest tests/test_permission_catalog.py`.

Una capacidad que ningún endpoint exige hace fallar el test **a propósito**:
concede autoridad nominal sobre algo que no existe.

---

## Migraciones

1. Toda modificación de esquema pasa por Alembic.
2. `uv run alembic -c app/alembic.ini revision --autogenerate -m "descripcion"`.
   **Revisar lo generado**: el autogenerate no acierta con índices parciales ni
   con claves foráneas compuestas.
3. Implementar `downgrade` siempre que el cambio sea razonablemente reversible.
4. Un solo head: `alembic heads` debe devolver uno.
5. Ninguna migración hace `DROP SCHEMA`.
6. Preservar los datos existentes cuando sea posible; si hay que interpretarlos
   (zonas horarias, valores por defecto), **documentar la interpretación en el
   docstring de la migración**.

---

## Lo que no se hace

- Introducir microservicios, bus de eventos, Kafka, RabbitMQ, CQRS, GraphQL,
  React Router, otro ORM, otro gestor de estado u otro framework de frontend.
  Las aplicaciones se integran por REST versionado y webhooks firmados.
- Desactivar un control para que pase un test.
- Usar SQLite en los tests: el esquema depende de índices únicos parciales,
  JSONB, claves foráneas compuestas y `timestamptz`.
- Confiar en `user_data` ni en ningún control del frontend.
- Duplicar en un módulo un dato canónico de otro (invariante 9).
- Editar o borrar filas de tablas append-only (`audit_event`,
  `integration_event`, `platform_audit_event`, `platform_health_check_run`).
  Las protegen disparadores; corregir es añadir una fila nueva.
- Aceptar del cuerpo de la petición quién actúa, en qué compañía o cuándo. Salen
  de la sesión autenticada, del subdominio y del reloj de la base.
- Aceptar un webhook sin verificar su firma, o procesarlo dos veces: la firma y
  la idempotencia están en `app/core/integration/webhooks.py`.
- Guardar un secreto en claro. Los de plataforma y los de webhooks se cifran con
  la llave maestra (`app/core/platform/secrets.py`).
- Escribir criptografía propia.
- Derivar la clave de almacenamiento del nombre que envía quien sube el archivo.
  La genera el servidor.
- Simular lo que no está construido: una pantalla sin backend dice que no existe
  en lugar de enseñar una lista vacía o un botón que no hace nada.
- Implementar dominios de negocio en la base. La base es plataforma; los dominios
  viven en la aplicación que los posee (`docs/DOMAIN_EXTENSION_GUIDE.md`).
- Reescribir el historial de git sin autorización explícita.

---

## Estilo de respuesta

1. Conciso y práctico.
2. Listar los archivos cambiados y por qué.
3. Indicar los comandos ejecutados y su resultado real.
4. Si algo no se pudo verificar, decirlo. "No lo he probado" nunca es "funciona".

---

## Reporte de ejecución

Estas reglas **complementan** las de arquitectura, testing, base de datos,
seguridad, Git y Definition of Done; no las sustituyen. El documento completo,
con plantillas y ejemplos, es
`_cer_delivery/progreso_y_reporte_de_ejecucion.md`.

1. **Reportar en hitos, no al final.** En trabajo largo —una implementación por
   fases, una migración, una regresión, un build, una validación de navegador—
   se informa cuando termina una fase, cuando termina un lote de tests, cuando
   aparece un problema, cuando se corrige, cuando falla algo, cuando hace falta
   una decisión humana y cuando empieza la validación final. **No** se narra
   cada comando.
2. **Lo importante, visible de inmediato**: qué está hecho, qué está corriendo,
   qué queda, qué riesgos o hallazgos hay.
3. **Evidencia concreta, nunca impresiones.** `24/24 PASS`, `0 errores`,
   `776 ejecutados, 0 fallos`, `exit 0`. Nada de "parece que funciona" ni "todo
   se ve bien". Lo que no se ejecutó se marca `PENDING`, `NOT RUN` o
   `NOT APPLICABLE`: **la evidencia ausente nunca se convierte en PASS.**
4. **`IMPLEMENTED` no es `VALIDATED`.** Un criterio de aceptación solo pasa a
   validado cuando existe la evidencia que lo respalda, y la evidencia se
   nombra junto al estado.
5. **Regresión grande, por lotes** cuando la arquitectura de tests lo permita:
   aísla el fallo y hace observable el avance. Por lote se registra nombre, nº
   de tests, resultado, exit code y duración, con acumulado.
6. **Un fallo nunca se esconde detrás de un verde global.** Se dice qué falló,
   por qué si está confirmado, el impacto, la acción y el estado actual. Si no
   se conoce la causa raíz, se dice — no se inventa. Tras corregir se reportan
   **las dos cosas**: que falló y que después pasó.
7. **Causas etiquetadas**: `CONFIRMED`, `LIKELY` o `UNVERIFIED`. Una suposición
   no se presenta como hecho.
8. **Hallazgos incidentales, a la vista.** Un problema descubierto fuera del
   cambio previsto se reporta cuando aparece, no enterrado en el resumen final,
   y con su **acción operativa** si algo tiene que ocurrir en otro sitio
   (bootstrap, migración, semillas, despliegue, revisión manual).
9. **Revisión humana separada de fallos de ingeniería.** Datos ambiguos,
   decisiones de negocio, aprobaciones y credenciales faltantes no son bugs.
10. **Migraciones**: revisión, resultado, head actual, nº de heads, y registros
    evaluados / modificados / omitidos / que requieren revisión humana. **Un
    dato de negocio ambiguo no se interpreta en silencio para que la migración
    termine**: se reporta.
11. **Local no es compartido.** Toda afirmación dice a qué entorno aplica. Una
    corrección local no arregla el entorno compartido.
12. **No se declara COMPLETED si falta validación.** Se distingue
    implementación terminada, validación en curso y validación completa; si
    queda algo, `COMPLETED WITH PENDING VALIDATION`.
13. **Reportar no autoriza alcance.** Terminado lo pedido y su validación: se
    emite el reporte final, se señalan la acción operativa pendiente y el
    siguiente paso natural, y se **para**. No se empieza otra cosa por
    iniciativa propia.
