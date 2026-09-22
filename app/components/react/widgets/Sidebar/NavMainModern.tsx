'use client';

import { useMemo } from 'react';
import { ChevronRight, type LucideIcon } from 'lucide-react';
import { useApp } from '@/app/providers/StoreProvider';
import { useVisibleNavigation } from '@/app/providers/maincontent/lib/useVisibleNavigation';
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
    SidebarGroup,
    SidebarGroupLabel,
    SidebarMenu,
    SidebarMenuButton,
    SidebarMenuItem,
    SidebarMenuSub,
    SidebarMenuSubButton,
    SidebarMenuSubItem,
} from '@/shared/ui/shadcn/new-york';

export interface INavMainSubItem {
    title: string;
    url: string;
    /**
     * Capacidad necesaria para abrir la pantalla.
     *
     * `AppSidebar` declaraba este campo por ítem, pero la interfaz de este
     * componente **no lo tenía** y nadie lo leía: los seis ítems se pintaban
     * para cualquier usuario autenticado (AUD-FE-001). TypeScript no protestaba
     * porque el objeto literal llegaba por un parámetro donde no aplica la
     * comprobación de propiedades sobrantes.
     *
     * Esto es experiencia de usuario, no seguridad: la cookie `user_data` de la
     * que salen los permisos es editable desde el navegador. La puerta real
     * está en el backend, que exige el mismo permiso para servir la página.
     */
    requiredPermission?: string;
    /** Reservado a administración de plataforma (`is_superuser`). */
    platformOnly?: boolean;
}

export interface INavMainItem {
    title: string;
    url: string;
    icon?: LucideIcon;
    isActive?: boolean;
    items?: INavMainSubItem[];
}

interface IProps {
    items: INavMainItem[];
}

export function NavMainModern({ items }: IProps) {
    const { appData } = useApp();
    const pathname = useMemo(() => window.location.pathname, []);

    // El filtro vive en un hook porque lo comparte el menu de usuario de la
    // barra superior: un permiso tiene que aplicarse igual en los dos menus.
    const visibleItems = useVisibleNavigation(items);

    return (
        <SidebarGroup className="pt-1">
            <SidebarGroupLabel className="px-2 text-xs font-semibold tracking-[0.06em] uppercase">
                {appData?.company_name || 'Navigation'}
            </SidebarGroupLabel>
            <SidebarMenu className="gap-1">
                {visibleItems.map((item) => {
                    const hasActiveChild = item.items.some((subItem) => pathname === subItem.url);
                    const isGroupOpen = item.isActive || hasActiveChild;

                    return (
                        <Collapsible
                            key={item.title}
                            asChild
                            defaultOpen={isGroupOpen}
                            className="group/collapsible"
                        >
                            <SidebarMenuItem>
                                <CollapsibleTrigger asChild>
                                    <SidebarMenuButton
                                        tooltip={item.title}
                                        isActive={hasActiveChild}
                                        className={[
                                            'h-10 rounded-lg px-2.5 text-[15px] font-medium',
                                            'text-muted-foreground transition-all',
                                            'hover:bg-accent hover:text-accent-foreground',
                                            'data-[active=true]:bg-accent',
                                            'data-[active=true]:text-accent-foreground',
                                        ].join(' ')}
                                    >
                                        {item.icon && <item.icon className="size-4" />}
                                        <span>{item.title}</span>
                                        <ChevronRight className="ml-auto size-4 transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" />
                                    </SidebarMenuButton>
                                </CollapsibleTrigger>
                                <CollapsibleContent>
                                    <SidebarMenuSub className="ml-4 mt-1 gap-1 border-l border-border pl-2.5">
                                        {item.items.map((subItem) => (
                                            <SidebarMenuSubItem key={subItem.title}>
                                                <SidebarMenuSubButton
                                                    asChild
                                                    isActive={pathname === subItem.url}
                                                    className={[
                                                        'h-9 rounded-lg px-2.5 text-[15px]',
                                                        'text-muted-foreground transition-all',
                                                        'hover:bg-accent hover:text-accent-foreground',
                                                        'data-[active=true]:bg-accent',
                                                        'data-[active=true]:font-medium',
                                                        'data-[active=true]:text-accent-foreground',
                                                    ].join(' ')}
                                                >
                                                    {/*
                                                      Enlace real, no un botón con
                                                      window.location: así el menú admite
                                                      clic central y "abrir en pestaña
                                                      nueva" (AUD-FE-021). Cada página es
                                                      una carga completa del servidor, que
                                                      es el patrón de esta aplicación.
                                                    */}
                                                    <a href={subItem.url}>
                                                        <span>{subItem.title}</span>
                                                    </a>
                                                </SidebarMenuSubButton>
                                            </SidebarMenuSubItem>
                                        ))}
                                    </SidebarMenuSub>
                                </CollapsibleContent>
                            </SidebarMenuItem>
                        </Collapsible>
                    );
                })}
            </SidebarMenu>
        </SidebarGroup>
    );
}
