import { CompanyProfileForm } from '@/features/Companies';
import { PageHeader } from '@/widgets/Layout';

const CompanyProfilePage = () => {
    return (
        <div className="flex flex-1 flex-col" data-testid="CompanyProfilePage">
            <PageHeader
                title="Company Profile"
                description="Contact details, branding, and workspace settings."
                breadcrumbs={[{ label: 'Administration' }, { label: 'Organization' }, { label: 'Company Profile' }]}
            />
            <div className="flex flex-1 flex-col gap-4 p-6">
                <CompanyProfileForm />
            </div>
        </div>
    );
};

export default CompanyProfilePage;
