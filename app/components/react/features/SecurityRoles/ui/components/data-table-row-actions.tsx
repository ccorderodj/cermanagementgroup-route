import * as React from 'react';
import { DotsHorizontalIcon } from '@radix-ui/react-icons';
import { Pencil, ShieldCheck, X } from 'lucide-react';
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
    DropdownMenuTrigger,
} from '@/shared/ui/shadcn/new-york';
import type { RoleEntity } from '@/entities/Roles';
import SecurityRoleForm from '../SecurityRoleForm';

interface DataTableRowActionsProps<TData> {
    row: Row<TData>;
    disabled?: boolean;
    onEdited: (data: RoleEntity) => void;
    onError: (message: string) => void;
}

export function DataTableRowActions<TData>(props: DataTableRowActionsProps<TData>) {
    const {
        row,
        disabled,
        onEdited,
        onError,
    } = props;
    const rowData = row.original as RoleEntity;
    const [isOpenPopup, setOpenPopup] = React.useState(false);

    const closeDialog = React.useCallback(() => {
        setOpenPopup(false);
    }, []);

    const openDialog = React.useCallback(() => {
        setOpenPopup(true);
    }, []);

    const getData = React.useCallback((data: RoleEntity) => {
        onEdited(data);
        closeDialog();
    }, [closeDialog, onEdited]);

    return (
        <>
            <Dialog open={isOpenPopup} onOpenChange={setOpenPopup}>
                <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-[980px] lg:max-w-[1100px]">
                    <DialogHeader>
                        <DialogTitle className="text-center">
                            <p className="inline-flex items-center gap-2">
                                <ShieldCheck className="h-4 w-4" />
                                Edit Role
                            </p>
                        </DialogTitle>
                        <DialogDescription />
                    </DialogHeader>

                    <SecurityRoleForm
                        getData={getData}
                        onError={onError}
                        initialData={rowData}
                        disabled={disabled}
                    />

                    <Button type="button" onClick={closeDialog}>
                        <X className="mr-2 h-4 w-4" />
                        Close
                    </Button>
                </DialogContent>
            </Dialog>

            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="ghost" className="flex h-8 w-8 p-0 data-[state=open]:bg-muted">
                        <DotsHorizontalIcon className="h-4 w-4" />
                        <span className="sr-only">Open menu</span>
                    </Button>
                </DropdownMenuTrigger>

                <DropdownMenuContent align="end" className="w-[160px]">
                    <DropdownMenuItem disabled={disabled} onClick={openDialog}>
                        <Pencil className="mr-2 h-4 w-4" />
                        Edit
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>
        </>
    );
}
