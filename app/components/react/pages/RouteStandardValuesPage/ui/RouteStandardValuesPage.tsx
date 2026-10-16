import { PageHeader } from '@/widgets/Layout';
import { StandardValuesPanel } from '@/features/RouteStandardValues';

const RouteStandardValuesPage = () => (
    <div className="flex flex-1 flex-col" data-testid="RouteStandardValuesPage">
        <PageHeader
            title="Standardized Lists"
            description="The selectable values supervisors choose from when they record what they did."
            breadcrumbs={[{ label: 'CER Route' }, { label: 'Configuration' }, { label: 'Standardized Lists' }]}
        />
        <div className="flex flex-1 flex-col p-6">
            <StandardValuesPanel />
        </div>
    </div>
);

export default RouteStandardValuesPage;
