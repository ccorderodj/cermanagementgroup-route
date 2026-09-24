import * as React from 'react';
import { DotsHorizontalIcon } from '@radix-ui/react-icons';
import {
    Pencil, Power, PowerOff, Trash2,
} from 'lucide-react';
import {
    Button,
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/shared/ui/shadcn/new-york';

/**
 * Acciones de fila **conscientes del estado**.
 *
 * El addendum RTE02-A01 es explícito: no se pintan
 * `Create / Update / Deactivate / Reactivate / Delete` como cinco botones
 * permanentes. Crear es una acción de página; en la fila queda `Edit` visible y
 * el resto en un menú contextual. Y lo que se ofrece depende del estado:
 *
 * * fila **activa**   -> Edit · Deactivate · Delete
 * * fila **inactiva** -> Edit · Reactivate · Delete
 *
 * Nunca las dos a la vez: ofrecer "Deactivate" sobre algo ya desactivado no
 * describe ninguna transición posible, y obliga a quien lo usa a adivinar en
 * qué estado está mirando.
 *
 * `Delete` va siempre al final, separado y en color destructivo, porque es la
 * única de las tres que no se deshace desde la pantalla.
 *
 * Esto es experiencia de usuario, no un control: quien tenga las capacidades
 * las tiene aunque el menú no muestre el botón, y quien no las tenga recibe 403
 * aunque lo vea (invariante 8 de AGENTS.md).
 */

interface LifecycleRowActionsProps {
    isActive: boolean;
    disabled?: boolean;
    onEdit?: () => void;
    onDeactivate?: () => void;
    onReactivate?: () => void;
    onDelete: () => void;
    /** Para nombrar la acción en su idioma: "Retire" en vez de "Deactivate". */
    labels?: {
        edit?: string;
        deactivate?: string;
        reactivate?: string;
        delete?: string;
    };
}

export function LifecycleRowActions(props: LifecycleRowActionsProps) {
    const {
        isActive, disabled, onEdit, onDeactivate, onReactivate, onDelete, labels,
    } = props;

    const texto = {
        edit: labels?.edit ?? 'Edit',
        deactivate: labels?.deactivate ?? 'Deactivate',
        reactivate: labels?.reactivate ?? 'Reactivate',
        delete: labels?.delete ?? 'Delete',
    };

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button
                    variant="ghost"
                    className="flex size-8 p-0 data-[state=open]:bg-muted"
                    disabled={disabled}
                >
                    <DotsHorizontalIcon className="size-4" />
                    <span className="sr-only">Open menu</span>
                </Button>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end" className="w-[190px]">
                {onEdit && (
                    <DropdownMenuItem disabled={disabled} onClick={onEdit}>
                        <Pencil className="mr-2 size-4" />
                        {texto.edit}
                    </DropdownMenuItem>
                )}

                {isActive && onDeactivate && (
                    <DropdownMenuItem disabled={disabled} onClick={onDeactivate}>
                        <PowerOff className="mr-2 size-4" />
                        {texto.deactivate}
                    </DropdownMenuItem>
                )}

                {!isActive && onReactivate && (
                    <DropdownMenuItem disabled={disabled} onClick={onReactivate}>
                        <Power className="mr-2 size-4" />
                        {texto.reactivate}
                    </DropdownMenuItem>
                )}

                <DropdownMenuSeparator />

                <DropdownMenuItem
                    disabled={disabled}
                    onClick={onDelete}
                    className="text-destructive focus:text-destructive"
                >
                    <Trash2 className="mr-2 size-4" />
                    {texto.delete}
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
