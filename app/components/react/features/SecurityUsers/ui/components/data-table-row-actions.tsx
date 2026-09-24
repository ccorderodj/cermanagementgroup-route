import * as React from 'react';
import { DotsHorizontalIcon } from '@radix-ui/react-icons';
import {
    Pencil, ShieldOff, ShieldCheck, Trash2, User, X,
} from 'lucide-react';
import type { Row } from '@tanstack/react-table';
import {
    Button,
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/shared/ui/shadcn/new-york';
import { ConfirmDestructiveDialog } from '@/features/Common';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import { useUser } from '@/app/providers/StoreProvider';
import {
    deleteUserManagement,
    setUserAccess,
    type UserManagementEntity,
} from '@/entities/UserManagement';
import SecurityUserForm from '../SecurityUserForm';

interface DataTableRowActionsProps<TData> {
    row: Row<TData>;
    disabled?: boolean;
    onEdited: (data: UserManagementEntity) => void;
    onDeleted?: (userId: number) => void;
    onError?: (message: string) => void;
}

export function DataTableRowActions<TData>(props: DataTableRowActionsProps<TData>) {
    const {
        row, disabled, onEdited, onDeleted, onError,
    } = props;

    const dispatch = useAppDispatch();
    const { userLogged, hasUserPermission } = useUser();
    const rowData = row.original as UserManagementEntity;
    const [isOpenPopup, setOpenPopup] = React.useState(false);
    const [isBusy, setBusy] = React.useState(false);
    const [confirmDelete, setConfirmDelete] = React.useState(false);
    const [blockedReason, setBlockedReason] = React.useState<string | null>(null);

    // Ocultar el botón es experiencia de usuario, no un control: quien no tenga
    // la capacidad recibe 403 aunque lo vea (invariante 8 de AGENTS.md). Se
    // oculta para no ofrecer una acción que va a fallar.
    const puedeBorrar = hasUserPermission('users.delete');

    // Nadie se retira a sí mismo. El servidor también lo rechaza; aquí se evita
    // ofrecer la acción que dejaría al administrador fuera de la pantalla en la
    // que está trabajando.
    const esUnoMismo = userLogged?.user_id === rowData.id;

    const closeDialog = React.useCallback(() => setOpenPopup(false), []);

    const getData = React.useCallback((data: UserManagementEntity) => {
        onEdited(data);
        closeDialog();
    }, [closeDialog, onEdited]);

    // Suspender no borra: conserva el registro y su historial.
    const toggleAccess = React.useCallback(async () => {
        setBusy(true);
        try {
            const updated = await dispatch(setUserAccess({
                userId: rowData.id,
                isActive: !rowData.is_active,
            })).unwrap();
            onEdited(updated);
        } catch (e) {
            onError?.(typeof e === 'string' ? e : 'Could not change user access');
        } finally {
            setBusy(false);
        }
    }, [dispatch, onEdited, onError, rowData.id, rowData.is_active]);

    /**
     * Retira a la persona de esta compañía. Un 409 no es un fallo genérico: es
     * el servidor explicando por qué no puede —retirarse a uno mismo—, y se
     * enseña en el mismo diálogo en vez de como un error suelto.
     */
    const borrar = React.useCallback(async () => {
        setBusy(true);
        try {
            await dispatch(deleteUserManagement({ userId: rowData.id })).unwrap();
            setConfirmDelete(false);
            onDeleted?.(rowData.id);
        } catch (e) {
            const mensaje = typeof e === 'string' ? e : 'Could not remove this user';
            if (mensaje.toLowerCase().includes('your own access')) {
                setBlockedReason(mensaje);
            } else {
                setConfirmDelete(false);
                onError?.(mensaje);
            }
        } finally {
            setBusy(false);
        }
    }, [dispatch, onDeleted, onError, rowData.id]);

    const cerrarBorrado = React.useCallback((abierto: boolean) => {
        if (!abierto) {
            setConfirmDelete(false);
            setBlockedReason(null);
        }
    }, []);

    return (
        <>
            <Dialog open={isOpenPopup} onOpenChange={setOpenPopup}>
                <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-[720px]">
                    <DialogHeader>
                        <DialogTitle className="inline-flex items-center gap-2">
                            <User className="size-4" />
                            Edit user
                        </DialogTitle>
                        <DialogDescription>
                            Personal details and role in this company.
                        </DialogDescription>
                    </DialogHeader>

                    <SecurityUserForm getData={getData} initialData={rowData} />

                    <Button type="button" variant="outline" onClick={closeDialog}>
                        <X className="mr-2 size-4" />
                        Close
                    </Button>
                </DialogContent>
            </Dialog>

            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="ghost" className="flex size-8 p-0 data-[state=open]:bg-muted">
                        <DotsHorizontalIcon className="size-4" />
                        <span className="sr-only">Open menu</span>
                    </Button>
                </DropdownMenuTrigger>

                <DropdownMenuContent align="end" className="w-[190px]">
                    <DropdownMenuItem disabled={disabled} onClick={() => setOpenPopup(true)}>
                        <Pencil className="mr-2 size-4" />
                        Edit
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                        disabled={disabled || isBusy}
                        onClick={toggleAccess}
                        className={rowData.is_active ? 'text-destructive focus:text-destructive' : ''}
                    >
                        {rowData.is_active ? (
                            <>
                                <ShieldOff className="mr-2 size-4" />
                                Suspend access
                            </>
                        ) : (
                            <>
                                <ShieldCheck className="mr-2 size-4" />
                                Restore access
                            </>
                        )}
                    </DropdownMenuItem>

                    {/* Borrar es otra cosa que suspender: suspender corta el
                        acceso y deja al usuario aquí; borrar lo saca de esta
                        pantalla. Va separado y al final por eso. */}
                    {puedeBorrar && !esUnoMismo && (
                        <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                                disabled={disabled || isBusy}
                                onClick={() => setConfirmDelete(true)}
                                className="text-destructive focus:text-destructive"
                            >
                                <Trash2 className="mr-2 size-4" />
                                Remove from company
                            </DropdownMenuItem>
                        </>
                    )}
                </DropdownMenuContent>
            </DropdownMenu>

            <ConfirmDestructiveDialog
                open={confirmDelete}
                onOpenChange={cerrarBorrado}
                title={`Remove ${rowData.email || rowData.username} from this company?`}
                description={(
                    <>
                        They lose access to this company immediately and stop
                        appearing in this list. Their account itself is not deleted —
                        it may belong to other companies — but under the current
                        model they cannot be added back here.
                        {' '}
                        To cut access temporarily instead, suspend them.
                    </>
                )}
                confirmLabel="Remove"
                blockedReason={blockedReason}
                busy={isBusy}
                onConfirm={borrar}
            />
        </>
    );
}
