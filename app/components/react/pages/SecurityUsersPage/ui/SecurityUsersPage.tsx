import { SecurityUsersPanel } from '@/features/SecurityUsers/ui/SecurityUsersPanel';
import { PageHeader } from '@/widgets/Layout';

const SecurityUsersPage = () => {
    return (
        <div className="flex flex-1 flex-col" data-testid="SecurityUsersPage">
            <PageHeader
                title="Users"
                description="Who has access to this workspace."
                breadcrumbs={[{ label: 'Administration' }, { label: 'Access control' }, { label: 'Users' }]}
            />
            <div className="flex flex-1 flex-col gap-4 p-6">
                <SecurityUsersPanel />
            </div>
        </div>
    );
};

export default SecurityUsersPage;
