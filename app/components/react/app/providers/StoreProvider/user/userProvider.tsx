import React, {
    createContext, useContext, useEffect, useState, ReactNode, useMemo,
} from 'react';
import CookieService from '@/shared/lib/utils/CookieService';

const checkUserPermission = (
    userLogged: UserLogged | null | undefined,
    permission: string,
): boolean => {
    if (!userLogged) return false;
    if (userLogged.is_superuser) return true;
    return userLogged.permissions?.includes(permission) || false;
};

const checkAnyUserPermission = (
    userLogged: UserLogged | null | undefined,
    permissions: string[],
): boolean => {
    if (!permissions.length) return true;
    return permissions.some((permission) => checkUserPermission(userLogged, permission));
};

type UserContextValue = {
    userLogged: UserLogged | null;
    setUserLogged: React.Dispatch<React.SetStateAction<UserLogged | null>>;
    hasUserPermission: (permission: string) => boolean;
    hasAnyUserPermission: (permissions: string[]) => boolean;
};

// Define the context
const UserContext = createContext<UserContextValue | null>(null);

// Provider Component
export const UserProvider = ({ children }: { children: ReactNode }) => {
    const [userLogged, setUserLogged] = useState<UserLogged | null>(null);

    useEffect(() => {
        // debugger
        const userLoggedJson = CookieService.getCookieValueJson<UserLogged>('user_data');
        if (userLoggedJson) {
            setUserLogged(userLoggedJson);
        }
    }, []);

    // Memoize the context value
    const contextValue = useMemo(
        () => ({
            userLogged,
            setUserLogged,
            hasUserPermission: (permission: string) => checkUserPermission(userLogged, permission),
            hasAnyUserPermission: (permissions: string[]) => checkAnyUserPermission(userLogged, permissions),
        }),
        [userLogged],
    );

    return (
        <UserContext.Provider value={contextValue}>
            {children}
        </UserContext.Provider>
    );
};

// Custom hook for easy access
export const useUser = () => {
    const context = useContext(UserContext);
    if (!context) {
        throw new Error('useUser must be used within a UserProvider');
    }
    return context;
};

export const useHasUserPermission = (
    permission: string,
): boolean => {
    const { hasUserPermission: checkPermission } = useUser();
    return checkPermission(permission);
};

export const useHasAnyUserPermission = (
    permissions: string[],
): boolean => {
    const { hasAnyUserPermission: checkPermissions } = useUser();
    return checkPermissions(permissions);
};

export const hasUserPermissionByUser = (
    userLogged: UserLogged | null | undefined,
    permission: string,
): boolean => {
    return checkUserPermission(userLogged, permission);
};

export const hasAnyUserPermissionByUser = (
    userLogged: UserLogged | null | undefined,
    permissions: string[],
): boolean => {
    return checkAnyUserPermission(userLogged, permissions);
};
