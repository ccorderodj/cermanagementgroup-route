import { SecurityRolesPanel } from '@/features/SecurityRoles/ui/SecurityRolesPanel';
import { PageHeader } from '@/widgets/Layout';

const SecurityRolesPage = () => {
    return (
        <div className="flex flex-1 flex-col" data-testid="SecurityRolesPage">
            <PageHeader
                title="Roles & Permissions"
                description="Define roles and the permissions they grant."
                breadcrumbs={[{ label: 'Administration' }, { label: 'Access control' }, { label: 'Roles & Permissions' }]}
            />
            <div className="flex flex-1 flex-col gap-4 p-6">
                <SecurityRolesPanel />
            </div>
        </div>
    );
};

export default SecurityRolesPage;
