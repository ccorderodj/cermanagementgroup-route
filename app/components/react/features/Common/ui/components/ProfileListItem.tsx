import type { ReactNode } from 'react';

interface ProfileListItemProps {
    title: ReactNode;
    lines?: ReactNode;
    actions?: ReactNode;
}

/**
 * Fila de las pestañas del perfil: título, un par de líneas de detalle y las
 * acciones a la derecha.
 *
 * Es el patrón `.item` del diseño aprobado. En pantallas estrechas las acciones
 * bajan bajo el texto en lugar de comprimirlo: el requisito pide que ninguna
 * acción importante dependa de un ancho que un teléfono no tiene.
 */
export const ProfileListItem = ({ title, lines, actions }: ProfileListItemProps) => (
    <li className="flex flex-col gap-3 border-b border-border py-3 last:border-b-0 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
            <p className="font-semibold">{title}</p>
            {lines && (
                <div className="mt-0.5 space-y-0.5 text-xs text-muted-foreground">
                    {lines}
                </div>
            )}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </li>
);
