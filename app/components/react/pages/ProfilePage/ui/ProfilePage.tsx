import { ProfileEditForm } from '@/features/Users';
import { PageHeader } from '@/widgets/Layout';

const ProfilePage = () => {
    return (
        <div
            className="flex flex-1 flex-col"
            data-testid="ProfilePage"
        >
            <PageHeader
                title="My Profile"
                description="Your account details and password."
                breadcrumbs={[{ label: 'My Profile' }]}
            />
            <div className="flex flex-1 flex-col gap-4 p-6">
                <ProfileEditForm />
            </div>
        </div>
    );
};

export default ProfilePage;
