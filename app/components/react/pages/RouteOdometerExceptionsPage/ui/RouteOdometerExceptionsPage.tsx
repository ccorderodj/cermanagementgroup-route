import { PageHeader } from '@/widgets/Layout';
import { OdometerExceptionsPanel } from '@/features/RouteOdometer';

const RouteOdometerExceptionsPage = () => (
    <div className="flex flex-1 flex-col" data-testid="RouteOdometerExceptionsPage">
        <PageHeader
            title="Odometer Exceptions"
            description="Supervisors who could not photograph the odometer and are asking to type the reading."
            breadcrumbs={[{ label: 'CER Route' }, { label: 'Configuration' }, { label: 'Odometer Exceptions' }]}
        />
        <div className="flex flex-1 flex-col p-6">
            <OdometerExceptionsPanel />
        </div>
    </div>
);

export default RouteOdometerExceptionsPage;
