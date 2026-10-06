import {
    Building2,
    Car,
    Route,
    Server,
    ShieldCheck,
} from 'lucide-react';
import type { INavMainItem } from '@/widgets/Sidebar';

/**
 * Qué se navega, en un solo sitio.
 *
 * Dos menús y una regla: **el menú lateral es para el trabajo de negocio; la
 * administración del sistema vive en el menú de usuario de la barra superior**
 *. Mezclarlas obliga a quien hace su trabajo diario a pasar por Security y
 * Platform para llegar a él.
 *
 * Los dos menús usan el mismo tipo y el mismo filtro (`useVisibleNavigation`),
 * así que un permiso se aplica igual en ambos. `tests/test_navigation_wiring.py`
 * lee este archivo: cada destino tiene que existir, cada permiso tiene que estar
 * en el catálogo y ninguna ruta de administración puede volver al menú lateral.
 *
 * `requiredPermission` es experiencia de usuario, no seguridad: el backend exige
 * el mismo permiso para servir cada página.
 */

/**
 * El trabajo de negocio de la aplicación. **Vacío en la base**: cada módulo de
 * dominio añade aquí su grupo cuando entrega su primera pantalla funcional.
 * Un encabezado sin destinos es un enlace muerto disfrazado de sección, así que
 * no se declara nada por adelantado (ver `docs/DOMAIN_EXTENSION_GUIDE.md`).
 *
 * `AdminPage` construye sus tarjetas de inicio desde esta misma lista, de modo
 * que menú e inicio no pueden divergir.
 */
export const businessNavigation: INavMainItem[] = [
    {
        // El trabajo de campo, **separado de la configuración y primero**.
        //
        // Las dos cosas estaban en un solo grupo y eso dejaba a `My Route`
        // fuera del menú: los cinco destinos de configuración exigen
        // capacidades de administración, así que el Supervisor —que sólo
        // ejecuta— no veía ningún ítem, el grupo entero desaparecía por estar
        // vacío, y a su propia pantalla sólo se llegaba escribiendo la URL.
        //
        // Un grupo aparte lo hace distinguible de la administración sin
        // duplicar la experiencia: los dos roles abren la misma pantalla.
        title: 'CER Route',
        url: '#',
        icon: Route,
        items: [
            {
                // La capacidad con la que se ejecuta la jornada, el viaje y la
                // parada. No hay una `route.myroute.read`: sería una segunda
                // forma de autorizar lo mismo.
                title: 'My Route',
                url: '/route',
                requiredPermission: 'route.worksession.execute',
            },
            {
                // El estado operativo del día. Es de administración: el
                // supervisor ejecuta su jornada, no vigila la de los demás,
                // así que pide `route.live.read` y no la capacidad de ejecución.
                title: 'Today / Live',
                url: '/admin/route/today',
                requiredPermission: 'route.live.read',
            },
        ],
    },
    {
        // Configuración operativa de CER Route. Activity y Reports **no** están
        // aquí: sus módulos llegan en checkpoints posteriores, y un encabezado
        // con destinos que no existen es un enlace muerto disfrazado de
        // sección. Today / Live sí está, en el grupo de trabajo, porque es
        // operación y no configuración.
        title: 'CER Route Configuration',
        url: '#',
        icon: Car,
        items: [
            {
                // Identidad del tenant, administrada con las capacidades del
                // núcleo. No hay un permiso `route.users.*`: sería una segunda
                // forma de autorizar lo mismo.
                title: 'Users',
                url: '/admin/route/users',
                requiredPermission: 'users.read',
            },
            {
                title: 'Supervisors',
                url: '/admin/route/supervisors',
                requiredPermission: 'route.vehicles.read',
            },
            {
                title: 'Vehicles',
                url: '/admin/route/vehicles',
                requiredPermission: 'route.vehicles.read',
            },
            {
                title: 'Standardized Lists',
                url: '/admin/route/standard-values',
                requiredPermission: 'route.standardvalues.manage',
            },
            {
                title: 'Odometer Exceptions',
                url: '/admin/route/odometer-exceptions',
                // La misma capacidad que exige la pagina en el servidor y que
                // exigen los endpoints de decision. No `route.vehicles.read`:
                // ver la flota no autoriza a decidir sobre su evidencia.
                requiredPermission: 'route.records.adjust',
            },
        ],
    },
];

export const administrationNavigation: INavMainItem[] = [
    {
        title: 'Organization',
        url: '#',
        icon: Building2,
        items: [
            {
                title: 'Company Profile',
                url: '/admin/companies/profile',
                requiredPermission: 'companies.read',
            },
            {
                title: 'Operating States',
                url: '/admin/locations/states',
                requiredPermission: 'regions.read',
            },
        ],
    },
    {
        title: 'Access control',
        url: '#',
        icon: ShieldCheck,
        items: [
            {
                title: 'Users',
                url: '/admin/security/users/list',
                requiredPermission: 'users.read',
            },
            {
                title: 'Roles & Permissions',
                url: '/admin/security/roles/list',
                requiredPermission: 'roles.read',
            },
            {
                title: 'Permissions',
                url: '/admin/security/permissions/list',
                requiredPermission: 'permissions.read',
            },
            {
                title: 'Permission Requests',
                url: '/admin/security/role-permission-requests/list',
                // El endpoint que consume la pantalla exige
                // `rolepermissionsapprovals.read`, no `rolepermissions.read`.
                // Pedir aqui uno distinto hacia visible un enlace que despues
                // devolvia 403 (AUD-FE-013).
                requiredPermission: 'rolepermissionsapprovals.read',
            },
        ],
    },
    {
        // Configuracion del despliegue, no de un tenant. No se rige por un
        // permiso del catalogo: ese catalogo se concede *dentro* de una
        // compania (D6), y un permiso aqui dejaria que el dueno de un tenant
        // viera la configuracion de todos.
        title: 'Platform',
        url: '#',
        icon: Server,
        items: [
            {
                title: 'Integrations & Settings',
                url: '/admin/platform/settings',
                platformOnly: true,
            },
            {
                title: 'Diagnostics',
                url: '/admin/platform/diagnostics',
                platformOnly: true,
            },
            {
                title: 'Companies',
                url: '/admin/companies/list',
                platformOnly: true,
            },
        ],
    },
];
