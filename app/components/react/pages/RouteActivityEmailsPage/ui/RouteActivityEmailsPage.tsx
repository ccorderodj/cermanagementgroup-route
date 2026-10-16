import { PageHeader } from '@/widgets/Layout';
import { ActivityEmailsPanel } from '@/features/RouteActivityEmails';

const RouteActivityEmailsPage = () => (
    <div className="flex flex-1 flex-col" data-testid="RouteActivityEmailsPage">
        <PageHeader
            title="Activity Emails"
            description="Motivational emails that recognize each person's everyday activity."
            breadcrumbs={[{ label: 'CER Route' }, { label: 'Configuration' }, { label: 'Activity Emails' }]}
        />
        <div className="flex flex-1 flex-col p-4 sm:p-6">
            <ActivityEmailsPanel />
        </div>
    </div>
);

export default RouteActivityEmailsPage;
