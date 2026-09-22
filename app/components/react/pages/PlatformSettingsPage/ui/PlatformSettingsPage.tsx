import { PlatformSettingsPanel } from '@/features/PlatformSettings';
import { PageHeader } from '@/widgets/Layout';

const PlatformSettingsPage = () => {
    return (
        <div className="flex flex-1 flex-col" data-testid="PlatformSettingsPage">
            <PageHeader
                title="Integrations & Settings"
                description="Connect the services production needs, store their credentials, and set platform policies."
                breadcrumbs={[{ label: 'Administration' }, { label: 'Platform' }, { label: 'Integrations & Settings' }]}
            />
            <div className="flex flex-1 flex-col gap-4 p-4 sm:p-6">
                <PlatformSettingsPanel />
            </div>
        </div>
    );
};

export default PlatformSettingsPage;
