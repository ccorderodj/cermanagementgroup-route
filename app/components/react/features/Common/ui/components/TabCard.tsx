import type { ReactNode } from 'react';

import { Card } from '@/shared/ui/shadcn/new-york';

interface TabCardProps {
    title: string;
    subtitle?: string;
    action?: ReactNode;
    canRead?: boolean;
    isLoading?: boolean;
    error?: string;
    isEmpty?: boolean;
    emptyMessage?: string;
    children: ReactNode;
}

/**
 * Tarjeta de una pestaña del perfil: cabecera con título, subtítulo y acción,
 * y debajo la lista.
 *
 * Los tres estados —cargando, error y vacío— se resuelven en un solo sitio.
 * Repetidos en cada pestaña acababan diciendo cosas distintas para lo mismo.
 */
export const TabCard = ({
    title,
    subtitle,
    action,
    canRead = true,
    isLoading = false,
    error,
    isEmpty = false,
    emptyMessage = 'Nothing recorded yet.',
    children,
}: TabCardProps) => (
    <Card className="p-4">
        <div className="flex flex-col gap-2 border-b border-border pb-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
                <h3 className="text-sm font-semibold">{title}</h3>
                {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
            </div>
            {canRead && action}
        </div>

        {/* Sin permiso de lectura se dice que no hay acceso. Enseñar una lista
            vacía haría creer que el cliente no tiene nada registrado. */}
        {!canRead && (
            <p className="pt-3 text-sm text-muted-foreground">
                You do not have permission to view this information.
            </p>
        )}

        {canRead && error && <p className="pt-3 text-sm text-destructive">{error}</p>}

        {canRead && isLoading && !error && (
            <p className="pt-3 text-sm text-muted-foreground">Loading...</p>
        )}

        {canRead && !isLoading && !error && isEmpty && (
            <p className="pt-3 text-sm text-muted-foreground">{emptyMessage}</p>
        )}

        {canRead && !isLoading && !error && !isEmpty && (
            <ul className="pt-1">{children}</ul>
        )}
    </Card>
);
