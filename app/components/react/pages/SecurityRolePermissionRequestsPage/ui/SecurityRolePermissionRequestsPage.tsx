import { SecurityRolePermissionRequestsPanel } from '@/features/SecurityRolePermissionRequests/ui/SecurityRolePermissionRequestsPanel';
import { PageHeader } from '@/widgets/Layout';

const SecurityRolePermissionRequestsPage = () => {
    return (
        <div className="flex flex-1 flex-col" data-testid="SecurityRolePermissionRequestsPage">
            <PageHeader
                title="Permission Requests"
                description="Approve or reject requests to grant extra permissions."
                breadcrumbs={[{ label: 'Administration' }, { label: 'Access control' }, { label: 'Permission Requests' }]}
            />
            <div className="flex flex-1 flex-col gap-4 p-6">
                <SecurityRolePermissionRequestsPanel />
            </div>
        </div>
    );
};

export default SecurityRolePermissionRequestsPage;
