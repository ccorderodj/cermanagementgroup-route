import { RouteMobileShell } from '@/widgets/RouteShell';
import { ActivityExplorerPanel } from '@/widgets/RouteActivityExplorer';

/**
 * Activity del supervisor (`/route/activity`, RTE08 personal).
 *
 * Su propia historia, por Day / Week / Month / Year, con el mismo explorador
 * que la vista de administración y dentro del shell de My Route. **Sin
 * selector de supervisor**: el servidor decide el sujeto con la sesión
 * (`GET /api/activity-explorer/me`), así que no hay nada que elegir ni un
 * directorio que mostrar. Sólo lectura.
 */
const RouteActivityPage = () => (
    <RouteMobileShell title="Activity" active="activity">
        <div data-testid="RouteActivityPage" className="flex flex-col">
            <ActivityExplorerPanel scope="self" />
        </div>
    </RouteMobileShell>
);

export default RouteActivityPage;
