import { useState } from 'react';
import { useApp } from '@/app/providers/StoreProvider';
import { SidebarMenu, SidebarMenuItem } from '@/shared/ui/shadcn/new-york';

export function SidebarBrand() {
    const { appData, companyLogo } = useApp();
    const [isLogoVisible, setIsLogoVisible] = useState(true);
    const showLogo = Boolean(companyLogo) && isLogoVisible;

    return (
        <SidebarMenu>
            <SidebarMenuItem>
                <a
                    href="/"
                    className={`flex w-full items-center rounded-lg px-2 py-2 transition-colors hover:bg-slate-100/80 ${showLogo ? 'justify-center' : 'justify-start'}`}
                >
                    {showLogo ? (
                        <img
                            src={companyLogo}
                            alt={`${appData?.company_name || 'Company'} logo`}
                            className="h-8 w-auto rounded-md object-contain"
                            onError={() => setIsLogoVisible(false)}
                        />
                    ) : (
                        <span className="truncate text-[15px] font-semibold tracking-tight text-slate-900">
                            {appData?.company_name || 'Company'}
                        </span>
                    )}
                </a>
            </SidebarMenuItem>
        </SidebarMenu>
    );
}
