import { OperatingStatesPanel } from '@/features/Regions';
import { PageHeader } from '@/widgets/Layout';

const LocationsStatesPage = () => (
    <div className="flex flex-1 flex-col" data-testid="LocationsStatesPage">
        <PageHeader
            title="Operating States"
            description="Territories where the operation runs."
            breadcrumbs={[{ label: 'Administration' }, { label: 'Organization' }, { label: 'Operating States' }]}
        />
        <div className="flex flex-1 flex-col p-6">
            <OperatingStatesPanel />
        </div>
    </div>
);

export default LocationsStatesPage;
