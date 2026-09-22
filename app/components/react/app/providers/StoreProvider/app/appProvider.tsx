import React, {
    createContext,
    useContext,
    useEffect,
    useState,
    ReactNode,
    useMemo,
} from 'react';

import CookieService from '@/shared/lib/utils/CookieService';
import { hexToHslTriple } from '@/shared/lib/utils/utils';

type AppContextValue = {
    appData: AppData | null;
    setAppData: React.Dispatch<React.SetStateAction<AppData | null>>;
    companyLogo: string | undefined;
};

// Create context
const AppContext = createContext<AppContextValue | null>(null);

// Provider Component
export const AppProvider = ({ children }: { children: ReactNode }) => {
    const [appData, setAppData] = useState<AppData | null>(null);

    const isValidLogoPath = useMemo(
        () => (path?: string): path is string => {
            if (!path) return false;
            const normalized = path.trim();
            if (!normalized.startsWith('/static/')) return false;
            return /\.(png|jpg|jpeg|svg|webp)$/i.test(normalized);
        },
        [],
    );

    // El logo cargado en Company Profile (appData.logo_url) manda; el de la
    // identidad del proyecto (APP_LOGO_PATH) es el respaldo.
    const isValidLogoUrl = useMemo(
        () => (value?: string | null): value is string => {
            if (!value) return false;
            const normalized = value.trim();
            return /^(https?:\/\/|\/static\/)/i.test(normalized);
        },
        [],
    );

    const companyLogo = useMemo(
        () => {
            if (isValidLogoUrl(appData?.logo_url)) return appData?.logo_url as string;
            return isValidLogoPath(appData?.logo_path) ? appData?.logo_path : undefined;
        },
        [appData?.logo_url, appData?.logo_path, isValidLogoPath, isValidLogoUrl],
    );

    useEffect(() => {
        const json = CookieService.getCookieValueJson<AppData>('app_data');
        if (json) {
            setAppData(json);
        }
    }, []);

    // La paleta configurada en Company Profile debe verse en la app, no solo
    // guardarse: sobreescribe los tokens shadcn en tiempo real.
    useEffect(() => {
        const root = document.documentElement.style;
        const primaryHsl = hexToHslTriple(appData?.brand_primary_color);
        const ringHsl = hexToHslTriple(appData?.brand_secondary_color);

        if (primaryHsl) {
            root.setProperty('--primary', primaryHsl);
        } else {
            root.removeProperty('--primary');
        }

        if (ringHsl) {
            root.setProperty('--ring', ringHsl);
        } else {
            root.removeProperty('--ring');
        }
    }, [appData?.brand_primary_color, appData?.brand_secondary_color]);

    const contextValue = useMemo(
        () => ({
            appData,
            setAppData,
            companyLogo,
        }),
        [appData, companyLogo],
    );

    return (
        <AppContext.Provider value={contextValue}>
            {children}
        </AppContext.Provider>
    );
};

// Custom hook
export const useApp = () => {
    const context = useContext(AppContext);
    if (!context) {
        throw new Error('useApp must be used within an AppProvider');
    }
    return context;
};
