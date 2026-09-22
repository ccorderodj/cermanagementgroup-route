import {
    CSSProperties,
    useEffect,
    useState,
} from 'react';
import { useApp } from "@/app/providers/StoreProvider";
import { getSafeHexColor } from '@/shared/lib/utils/utils';

function NavBar() {
    const { appData, companyLogo } = useApp();
    const [isLogoVisible, setIsLogoVisible] = useState(true);

    useEffect(() => {
        setIsLogoVisible(true);
    }, [companyLogo]);

    const navStyle = {
        '--company-navbar-dark-bg': getSafeHexColor(appData?.brand_primary_color, '#1f2937'),
        '--company-navbar-dark-border': getSafeHexColor(appData?.brand_secondary_color, '#374151'),
    } as CSSProperties;

    return (
        <nav
            style={navStyle}
            className="fixed z-30 w-full bg-white border-b border-gray-200 dark:bg-[var(--company-navbar-dark-bg)] dark:border-[var(--company-navbar-dark-border)]"
        >
            <div
                className="px-3 py-3 lg:px-5 lg:pl-3 ">
                <div className="flex items-center justify-between">
                    <div className="flex items-center justify-start">
                        <a href="/" className="flex ml-2 md:mr-24">
                            <span
                                className="self-center flex items-center gap-2 text-xl font-semibold sm:text-2xl whitespace-nowrap dark:text-white">
                                {companyLogo && isLogoVisible && (
                                    <img
                                        src={companyLogo}
                                        alt={`${appData?.company_name || 'Company'} logo`}
                                        className="h-8 w-auto rounded-sm"
                                        onError={() => setIsLogoVisible(false)}
                                    />
                                )}
                                {/* <span>{appData?.company_name}</span> */}
                            </span>
                        </a>
                    </div>
                    {appData?.mode === "DEV" && (
                        <span className="text-white">
                            🚧 Ambiente de prueba TEST | You are development Mode Active
                        </span>
                    )}
                    <div className="flex items-center">
                        <div className="flex items-center ml-3">
                            <div>

                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </nav >
    )
}

export {
    NavBar
}
