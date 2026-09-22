import { DiagnosticsPanel } from '@/features/PlatformSettings';
import { PageHeader } from '@/widgets/Layout';

const PlatformDiagnosticsPage = () => {
    return (
        <div className="flex flex-1 flex-col" data-testid="PlatformDiagnosticsPage">
            <PageHeader
                title="Diagnostics"
                description="Whether each configured service works, and whether evidence is still protected."
                breadcrumbs={[{ label: 'Administration' }, { label: 'Platform' }, { label: 'Diagnostics' }]}
            />
            <div className="flex flex-1 flex-col gap-4 p-4 sm:p-6">
                <DiagnosticsPanel />
            </div>
        </div>
    );
};

export default PlatformDiagnosticsPage;
