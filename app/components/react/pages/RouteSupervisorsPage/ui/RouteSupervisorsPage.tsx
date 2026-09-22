import { PageHeader } from '@/widgets/Layout';
import { SupervisorSetupPanel } from '@/features/RouteVehicles';

/**
 * Supervisores: designación y asignación de vehículo.
 *
 * Aquí se ve y se opera la cadena `usuario -> supervisor -> vehículo` sin
 * tocar la API a mano, que era la brecha que este cierre resuelve.
 */
const RouteSupervisorsPage = () => (
    <div className="flex flex-1 flex-col" data-testid="RouteSupervisorsPage">
        <PageHeader
            title="Supervisors"
            description="Who does field work in CER Route, and which vehicle they drive."
            breadcrumbs={[{ label: 'CER Route' }, { label: 'Configuration' }, { label: 'Supervisors' }]}
        />
        <div className="flex flex-1 flex-col p-6">
            <SupervisorSetupPanel />
        </div>
    </div>
);

export default RouteSupervisorsPage;
