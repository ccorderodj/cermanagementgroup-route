import * as React from 'react';
import { NavMainModern, SidebarBrand } from '@/widgets/Sidebar';
import {
    Sidebar,
    SidebarContent,
    SidebarHeader,
} from '@/shared/ui/shadcn/new-york';
import { useUser } from '@/app/providers/StoreProvider';
import { businessNavigation } from '@/app/providers/maincontent/config/navigation';

/**
 * Menú lateral: **sólo el trabajo de negocio** (D12-03, fase 12).
 *
 * Los destinos viven en `config/navigation.ts`, que comparte con el menú de
 * usuario de la barra superior, donde está ahora la administración del sistema.
 * Este archivo no declara rutas propias: si lo hiciera volvería a haber dos
 * listas, y `tests/test_navigation_wiring.py` lo impide.
 */
export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
    const { userLogged } = useUser();

    if (!userLogged) {
        return null;
    }

    return (
        <Sidebar
            {...props}
            className="overflow-hidden border-r border-border bg-card"
        >
            <SidebarHeader className="border-b border-border px-2 pb-2 pt-2">
                <SidebarBrand />
            </SidebarHeader>
            <SidebarContent className="px-1 py-2">
                <NavMainModern items={businessNavigation} />
            </SidebarContent>
        </Sidebar>
    );
}
