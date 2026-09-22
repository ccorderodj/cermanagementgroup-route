import { ReactNode } from 'react';
import { ComponentRoot } from '../ui/maincontent';

// Acceso y cuenta
import { LoginPage } from '@/pages/LoginPage';
import { PasswordResetPage } from '@/pages/PasswordResetPage';
import { ChangePasswordPage } from '@/pages/ChangePasswordPage';
import { ProfilePage } from '@/pages/ProfilePage';

// Generales
import { AdminPage } from '@/pages/AdminPage';

// Organización
import { CompanyListPage } from '@/pages/CompanyListPage';
import { CompanyProfilePage } from '@/pages/CompanyProfilePage';
import { LocationsStatesPage } from '@/pages/LocationsStatesPage';

// Seguridad
import { SecurityUsersPage } from '@/pages/SecurityUsersPage';
import { SecurityRolesPage } from '@/pages/SecurityRolesPage';
import { SecurityPermissionsPage } from '@/pages/SecurityPermissionsPage';
import { SecurityRolePermissionRequestsPage } from '@/pages/SecurityRolePermissionRequestsPage';

// Plataforma
import { PlatformSettingsPage } from '@/pages/PlatformSettingsPage';
import { PlatformDiagnosticsPage } from '@/pages/PlatformDiagnosticsPage';

// CER Route
import { RouteMyRoutePage } from '@/pages/RouteMyRoutePage';
import { RouteActivityPage } from '@/pages/RouteActivityPage';
import { RouteMePage } from '@/pages/RouteMePage';
import { RouteVehiclesPage } from '@/pages/RouteVehiclesPage';
import { RouteStandardValuesPage } from '@/pages/RouteStandardValuesPage';

/**
 * Mapa clave de página -> componente.
 *
 * La clave viene del atributo `data-current-page` que el servidor imprime en
 * la plantilla Jinja, y que a su vez sale del `name=` de la ruta FastAPI.
 * Ver `maincontent.ts` y `docs/ARCHITECTURE.md`.
 */
export const RootComponents: Record<string, ReactNode> = {
    [ComponentRoot.LOGIN]: <LoginPage />,
    [ComponentRoot.PASSWORDRESET]: <PasswordResetPage />,
    [ComponentRoot.CHANGEPASSWORD]: <ChangePasswordPage />,
    [ComponentRoot.PROFILE]: <ProfilePage />,

    [ComponentRoot.ADMIN]: <AdminPage />,

    [ComponentRoot.COMPANYLIST]: <CompanyListPage />,
    [ComponentRoot.COMPANYPROFILE]: <CompanyProfilePage />,
    [ComponentRoot.LOCATIONSSTATES]: <LocationsStatesPage />,

    [ComponentRoot.SECURITYUSERS]: <SecurityUsersPage />,
    [ComponentRoot.SECURITYROLES]: <SecurityRolesPage />,
    [ComponentRoot.SECURITYPERMISSIONS]: <SecurityPermissionsPage />,
    [ComponentRoot.SECURITYROLEPERMISSIONREQUESTS]: <SecurityRolePermissionRequestsPage />,

    [ComponentRoot.PLATFORMSETTINGS]: <PlatformSettingsPage />,
    [ComponentRoot.PLATFORMDIAGNOSTICS]: <PlatformDiagnosticsPage />,

    [ComponentRoot.ROUTEMYROUTE]: <RouteMyRoutePage />,
    [ComponentRoot.ROUTEACTIVITY]: <RouteActivityPage />,
    [ComponentRoot.ROUTEME]: <RouteMePage />,
    [ComponentRoot.ROUTEVEHICLES]: <RouteVehiclesPage />,
    [ComponentRoot.ROUTESTANDARDVALUES]: <RouteStandardValuesPage />,
};
