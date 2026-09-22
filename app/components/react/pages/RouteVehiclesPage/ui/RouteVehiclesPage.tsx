import { PageHeader } from '@/widgets/Layout';
import { VehiclesPanel } from '@/features/RouteVehicles';

/**
 * Maestro de vehículos: alta, edición, retirada y restauración.
 *
 * Las asignaciones viven en su propia pantalla (Supervisors), porque son la
 * relación `usuario -> designación -> vehículo` y no una propiedad del
 * vehículo.
 */
const RouteVehiclesPage = () => (
    <div className="flex flex-1 flex-col" data-testid="RouteVehiclesPage">
        <PageHeader
            title="Vehicles"
            description="The vehicles this company operates."
            breadcrumbs={[{ label: 'CER Route' }, { label: 'Configuration' }, { label: 'Vehicles' }]}
        />
        <div className="flex flex-1 flex-col p-6">
            <VehiclesPanel />
        </div>
    </div>
);

export default RouteVehiclesPage;
