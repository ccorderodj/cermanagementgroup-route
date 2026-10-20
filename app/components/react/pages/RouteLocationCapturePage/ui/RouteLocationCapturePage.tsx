import { PageHeader } from '@/widgets/Layout';
import { LocationCaptureSettings } from '@/features/RouteLocationCapture';

const RouteLocationCapturePage = () => (
    <div className="flex flex-1 flex-col" data-testid="RouteLocationCapturePage">
        <PageHeader
            title="Location Capture"
            description="Periodic location points during the workday, in addition to the event points."
            breadcrumbs={[{ label: 'CER Route' }, { label: 'Configuration' }, { label: 'Location Capture' }]}
        />
        <div className="flex flex-1 flex-col p-4 sm:p-6">
            <LocationCaptureSettings />
        </div>
    </div>
);

export default RouteLocationCapturePage;
