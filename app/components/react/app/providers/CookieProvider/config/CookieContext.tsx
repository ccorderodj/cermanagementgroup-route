import React, { createContext, useContext, ReactNode } from 'react';
import CookieService from '@/shared/lib/utils/CookieService';

// Define the type for the context
interface CookieContextType {
    getCookie: (name: string) => string | null;
    setCookie: (name: string, value: string, days: number) => void;
    deleteCookie: (name: string) => void;
}

// Create the context with a default value
const CookieContext = createContext<CookieContextType | undefined>(undefined);

// Provider component to inject the cookie service
export const CookieProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    return (
        <CookieContext.Provider value={CookieService}>
            {children}
        </CookieContext.Provider>
    );
};

// Hook to use the CookieService from the context
export const useCookies = (): CookieContextType => {
    const context = useContext(CookieContext);
    if (!context) {
        throw new Error('useCookies must be used within a CookieProvider');
    }
    return context;
};
