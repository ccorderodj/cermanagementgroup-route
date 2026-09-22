import * as React from 'react';
import { DotsHorizontalIcon } from '@radix-ui/react-icons';
import {
    Pencil, ShieldOff, ShieldCheck, User, X,
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
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import { setUserAccess, type UserManagementEntity } from '@/entities/UserManagement';
import SecurityUserForm from '../SecurityUserForm';

interface DataTableRowActionsProps<TData> {
    row: Row<TData>;
    disabled?: boolean;
    onEdited: (data: UserManagementEntity) => void;
    onError?: (message: string) => void;
}

export function DataTableRowActions<TData>(props: DataTableRowActionsProps<TData>) {
    const {
        row, disabled, onEdited, onError,
    } = props;

    const dispatch = useAppDispatch();
    const rowData = row.original as UserManagementEntity;
    const [isOpenPopup, setOpenPopup] = React.useState(false);
    const [isBusy, setBusy] = React.useState(false);

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
                </DropdownMenuContent>
            </DropdownMenu>
        </>
    );
}
