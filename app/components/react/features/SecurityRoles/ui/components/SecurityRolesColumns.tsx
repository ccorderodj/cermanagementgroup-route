import type { ReactNode } from 'react';
import type { ColumnDef, Row, Table } from '@tanstack/react-table';
import type { RoleEntity } from '@/entities/Roles';

type SecurityRolesTableMeta = {
    renderRowActions?: (args: { row: Row<RoleEntity>; table: Table<RoleEntity> }) => ReactNode;
};

export const getSecurityRolesColumns = (): ColumnDef<RoleEntity>[] => {
    return [
        {
            accessorKey: 'id',
            header: 'ID',
        },
        {
            accessorKey: 'name',
            header: 'Name',
        },
        {
            accessorKey: 'description',
            header: 'Description',
            cell: ({ row }) => row.original.description || '-',
        },
        {
            accessorKey: 'is_active',
            header: 'Status',
            cell: ({ row }) => (row.original.is_active ? 'Active' : 'Inactive'),
        },
        {
            id: 'actions',
            header: 'Actions',
            cell: ({ row, table }) => {
                const meta = table.options.meta as SecurityRolesTableMeta | undefined;
                return meta?.renderRowActions?.({ row, table }) || null;
            },
        },
    ];
};
