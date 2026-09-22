import { SecurityPermissionsPanel } from '@/features/SecurityPermissions/ui/SecurityPermissionsPanel';
import { PageHeader } from '@/widgets/Layout';

const SecurityPermissionsPage = () => {
    return (
        <div className="flex flex-1 flex-col" data-testid="SecurityPermissionsPage">
            <PageHeader
                title="Permissions"
                description="Fine-grained control over every module action."
                breadcrumbs={[{ label: 'Administration' }, { label: 'Access control' }, { label: 'Permissions' }]}
            />
            <div className="flex flex-1 flex-col gap-4 p-6">
                <SecurityPermissionsPanel />
            </div>
        </div>
    );
};

export default SecurityPermissionsPage;
