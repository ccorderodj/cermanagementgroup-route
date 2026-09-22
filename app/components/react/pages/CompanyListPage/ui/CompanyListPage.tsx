import { CompanyTable } from '@/features/Companies';
import { PageHeader } from '@/widgets/Layout';

const CompanyListPage = () => {
    return (
        <div className="flex flex-1 flex-col" data-testid="CompanyListPage">
            <PageHeader
                title="Companies"
                description="Companies (tenants), their contact details and branding."
                breadcrumbs={[{ label: 'Administration' }, { label: 'Platform' }, { label: 'Companies' }]}
            />
            <div className="flex flex-1 flex-col gap-4 p-6">
                <CompanyTable />
            </div>
        </div>
    );
};

export default CompanyListPage;
