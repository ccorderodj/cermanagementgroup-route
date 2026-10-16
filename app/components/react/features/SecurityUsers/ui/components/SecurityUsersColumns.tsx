import type { ReactNode } from 'react';
import type { ColumnDef, Row, Table } from '@tanstack/react-table';
import { Badge } from '@/shared/ui/shadcn/new-york';
import type { UserManagementEntity } from '@/entities/UserManagement';

type SecurityUsersTableMeta = {
    renderRowActions?: (args: { row: Row<UserManagementEntity>; table: Table<UserManagementEntity> }) => ReactNode;
};

/** Fecha corta y legible; `-` cuando nunca ha entrado. */
const formatLastLogin = (value?: string | null): string => {
    if (!value) return 'Never';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '-';
    return date.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });
};

/**
 * Columnas de la pantalla de usuarios.
 *
 * El rol llega ya resuelto desde el backend (`role_name`): la tabla puente
 * `user_company` no se administra por separado.
 */
export const getSecurityUsersColumns = (): ColumnDef<UserManagementEntity>[] => [
    {
        accessorKey: 'first_name',
        header: 'Name',
        cell: ({ row }) => {
            const { first_name: firstName, last_name: lastName, username } = row.original;
            const fullName = [firstName, lastName].filter(Boolean).join(' ');
            return (
                <div className="min-w-0">
                    <div className="truncate font-medium">{fullName || username}</div>
                    <div className="truncate text-xs text-muted-foreground">@{username}</div>
                </div>
            );
        },
    },
    {
        accessorKey: 'email',
        header: 'Email',
        cell: ({ row }) => (
            <span className="text-sm">{row.original.email || '-'}</span>
        ),
    },
    {
        accessorKey: 'role_name',
        header: 'Role',
        cell: ({ row }) => {
            const { role_name: roleName, is_superuser: isSuperuser } = row.original;
            if (isSuperuser) {
                return <Badge className="capitalize">Superadmin</Badge>;
            }
            if (!roleName) {
                return <span className="text-sm text-muted-foreground">No role</span>;
            }
            return <Badge variant="secondary" className="capitalize">{roleName}</Badge>;
        },
    },
    {
        accessorKey: 'last_login',
        header: 'Last access',
        cell: ({ row }) => (
            <span className="text-sm text-muted-foreground">
                {formatLastLogin(row.original.last_login)}
            </span>
        ),
    },
    {
        accessorKey: 'is_active',
        header: 'Status',
        cell: ({ row }) => (
            row.original.is_active
                ? (
                    <span className="inline-flex items-center gap-1.5 text-sm">
                        <span className="size-1.5 rounded-full bg-success" />
                        Active
                    </span>
                )
                : (
                    <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
                        <span className="size-1.5 rounded-full bg-muted-foreground/50" />
                        Suspended
                    </span>
                )
        ),
    },
    {
        id: 'actions',
        header: '',
        cell: ({ row, table }) => {
            const meta = table.options.meta as SecurityUsersTableMeta | undefined;
            return meta?.renderRowActions?.({ row, table }) || null;
        },
    },
];
