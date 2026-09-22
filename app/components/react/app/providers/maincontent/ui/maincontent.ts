/**
 * Clave de página del patrón server-route + page-key.
 *
 * Cada valor debe coincidir EXACTAMENTE con el `name=` de la ruta FastAPI
 * correspondiente en `app/routers_pages/`. Ese mismo valor llega al DOM como
 * `data-current-page` y `AppMainContent` lo usa para buscar el componente en
 * `RootComponents` (ver `mainContentConfig.tsx`).
 *
 * Si el valor no existe en `RootComponents`, la página se queda en blanco
 * sin lanzar ningún error. Los tres sitios tienen que decir lo mismo.
 * `tests/test_page_wiring.py` lo comprueba. Para añadir una página de dominio,
 * ver `docs/DOMAIN_EXTENSION_GUIDE.md`.
 */
export enum ComponentRoot {
    // Acceso y cuenta
    LOGIN = 'LoginPage',
    PASSWORDRESET = 'PasswordResetPage',
    CHANGEPASSWORD = 'ChangePasswordPage',
    PROFILE = 'ProfilePage',

    // Generales
    ADMIN = 'AdminPage',

    // Organización
    COMPANYLIST = 'CompanyListPage',
    COMPANYPROFILE = 'CompanyProfilePage',
    LOCATIONSSTATES = 'LocationsStatesPage',

    // Seguridad
    SECURITYUSERS = 'SecurityUsersPage',
    SECURITYROLES = 'SecurityRolesPage',
    SECURITYPERMISSIONS = 'SecurityPermissionsPage',
    SECURITYROLEPERMISSIONREQUESTS = 'SecurityRolePermissionRequestsPage',

    // Plataforma: configuracion del despliegue, no del tenant.
    PLATFORMSETTINGS = 'PlatformSettingsPage',
    PLATFORMDIAGNOSTICS = 'PlatformDiagnosticsPage',
}
