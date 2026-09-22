import type { ReactNode } from 'react';
import type { ColumnDef, Row, Table } from '@tanstack/react-table';
import { ArrowDownCircle, ArrowUpCircle } from 'lucide-react';
import { Badge } from '@/shared/ui/shadcn/new-york';
import type { RolePermissionChangeRequestEntity } from '@/entities/RolePermissionChangeRequests';

type RequestsTableMeta = {
    renderRowActions?: (args: {
        row: Row<RolePermissionChangeRequestEntity>;
        table: Table<RolePermissionChangeRequestEntity>;
    }) => ReactNode;
};

const formatDate = (value?: string | null): string => {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '-';
    return date.toLocaleString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
};

const statusBadge = (status: string) => {
    if (status === 'approved') {
        return <Badge className="bg-success text-success-foreground hover:bg-success/90">Approved</Badge>;
    }
    if (status === 'rejected') {
        return <Badge variant="destructive">Rejected</Badge>;
    }
    return <Badge className="bg-warning text-warning-foreground hover:bg-warning/90">Pending</Badge>;
};

/**
 * Columnas de las solicitudes de cambio de permisos.
 *
 * Conceder y revocar se muestran **por separado**: son dos actividades
 * distintas y quien revisa necesita verlas como tales, no como un "cambio"
 * indistinto.
 */
export const getSecurityRolePermissionRequestsColumns = (): ColumnDef<RolePermissionChangeRequestEntity>[] => [
    {
        accessorKey: 'role_name',
        header: 'Role',
        cell: ({ row }) => {
            const { role_name: roleName, role_id: roleId, role_category: category } = row.original;
            return (
                <div className="min-w-0">
                    <div className="truncate font-medium capitalize">{roleName || `#${roleId}`}</div>
                    <div className="truncate text-xs capitalize text-muted-foreground">
                        {category || '-'}
                    </div>
                </div>
            );
        },
    },
    {
        id: 'changes',
        header: 'Requested changes',
        cell: ({ row }) => {
            const { to_grant: toGrant, to_revoke: toRevoke } = row.original;
            if (!toGrant.length && !toRevoke.length) {
                return <span className="text-sm text-muted-foreground">No effective change</span>;
            }
            return (
                <div className="space-y-1.5">
                    {toGrant.length > 0 && (
                        <div className="flex items-start gap-1.5">
                            <ArrowUpCircle className="mt-0.5 size-3.5 shrink-0 text-success" />
                            <span className="text-xs">
                                <span className="font-semibold text-success">Grant</span>
                                {' '}
                                {toGrant.join(', ')}
                            </span>
                        </div>
                    )}
                    {toRevoke.length > 0 && (
                        <div className="flex items-start gap-1.5">
                            <ArrowDownCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
                            <span className="text-xs">
                                <span className="font-semibold text-destructive">Revoke</span>
                                {' '}
                                {toRevoke.join(', ')}
                            </span>
                        </div>
                    )}
                </div>
            );
        },
    },
    {
        accessorKey: 'requested_by_user',
        header: 'Requested by',
        cell: ({ row }) => {
            const user = row.original.requested_by_user;
            const name = [user?.first_name, user?.last_name].filter(Boolean).join(' ');
            return (
                <div className="min-w-0">
                    <div className="truncate text-sm">{name || user?.username || '-'}</div>
                    <div className="truncate text-xs text-muted-foreground">
                        {formatDate(row.original.created_at)}
                    </div>
                </div>
            );
        },
    },
    {
        accessorKey: 'reviewed_by_user',
        header: 'Reviewed by',
        cell: ({ row }) => {
            const user = row.original.reviewed_by_user;
            if (!user) return <span className="text-sm text-muted-foreground">-</span>;
            const name = [user.first_name, user.last_name].filter(Boolean).join(' ');
            return <span className="text-sm">{name || user.username}</span>;
        },
    },
    {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => statusBadge(row.original.status),
    },
    {
        id: 'actions',
        header: '',
        cell: ({ row, table }) => {
            const meta = table.options.meta as RequestsTableMeta | undefined;
            return meta?.renderRowActions?.({ row, table }) || null;
        },
    },
];
