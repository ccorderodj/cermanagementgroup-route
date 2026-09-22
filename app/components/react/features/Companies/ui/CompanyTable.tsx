import { useEffect, useMemo, useState } from 'react';
import { useSelector } from 'react-redux';
import { ColumnDef } from '@tanstack/react-table';

import { DataTable, DataTablePagination, DataTableColumnHeader } from '@/features/Common';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import { useDebounce } from '@/shared/lib/hooks/useDebounce/useDebounce';
import { Badge, Input } from '@/shared/ui/shadcn/new-york';
import {
    type Company,
    companiesPaginationSliceActions,
    fetchCompaniesPageSize,
    fetchCompaniesPagination,
    fetchSetPageIndexCompanies,
    getCompaniesPaginationCount,
    getCompaniesPaginationData,
    getCompaniesPaginationError,
    getCompaniesPaginationIndexPage,
    getCompaniesPaginationIsLoading,
    getCompaniesPaginationPageSize,
} from '@/entities/Companies';

/**
 * Listado de compañías (tenants de la plataforma).
 *
 * Usa la **única** implementación de tabla del proyecto,
 * `features/Common/DataTable`. Antes esta pantalla arrastraba una copia
 * completa y paralela del sistema de tablas bajo
 * `features/Companies/ui/CompanyTable/ui/components/` —nueve archivos, de los
 * que siete no los referenciaba nadie, incluidos `data-table-toolbar-employee`
 * y `user-nav`, que ni siquiera pertenecían a este dominio (AUD-FE-004).
 *
 * La pantalla es de administración de plataforma: el backend solo la sirve a
 * `Users.is_superuser` (D6).
 */

const columns: ColumnDef<Company>[] = [
    {
        accessorKey: 'id',
        header: ({ column }) => <DataTableColumnHeader column={column} title="Id" />,
        cell: ({ row }) => <span className="text-muted-foreground">{row.getValue('id')}</span>,
        enableSorting: false,
    },
    {
        accessorKey: 'name',
        header: ({ column }) => <DataTableColumnHeader column={column} title="Company" />,
        cell: ({ row }) => (
            <span className="max-w-[420px] truncate font-medium">{row.getValue('name')}</span>
        ),
    },
    {
        accessorKey: 'subdomain',
        header: ({ column }) => <DataTableColumnHeader column={column} title="Subdomain" />,
        cell: ({ row }) => {
            const subdomain = row.getValue('subdomain') as string | null;
            return subdomain
                ? <code className="text-xs">{subdomain}</code>
                : <span className="text-xs text-muted-foreground">—</span>;
        },
    },
    {
        accessorKey: 'is_active',
        header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
        cell: ({ row }) => (
            row.getValue('is_active')
                ? <Badge variant="default">Active</Badge>
                : <Badge variant="secondary">Inactive</Badge>
        ),
    },
];

export default function CompanyTable() {
    const dispatch = useAppDispatch();

    const rows = useSelector(getCompaniesPaginationData);
    const count = useSelector(getCompaniesPaginationCount);
    const pageSize = useSelector(getCompaniesPaginationPageSize);
    const indexPage = useSelector(getCompaniesPaginationIndexPage);
    const isLoading = useSelector(getCompaniesPaginationIsLoading);
    const error = useSelector(getCompaniesPaginationError);

    const [search, setSearch] = useState('');

    const runSearch = useDebounce((value: string) => {
        dispatch(companiesPaginationSliceActions.setIndexPage(0));
        dispatch(fetchCompaniesPagination({ name: value || undefined }));
    }, 400);

    useEffect(() => {
        dispatch(fetchCompaniesPagination({}));
    }, [dispatch]);

    const tableState = useMemo(() => ({
        pagination: { pageIndex: indexPage, pageSize },
    }), [indexPage, pageSize]);

    return (
        <div className="space-y-4">
            <Input
                className="h-9 w-full sm:w-[280px]"
                placeholder="Search by name..."
                value={search}
                onChange={(event) => {
                    setSearch(event.target.value);
                    runSearch(event.target.value);
                }}
            />

            {error && <p className="text-sm text-destructive">{error}</p>}

            <DataTable
                columns={columns}
                data={rows ?? []}
                manualPagination
                totalRows={count ?? 0}
                enableRowSelection={false}
                state={tableState}
                emptyMessage={isLoading ? 'Loading…' : 'No companies found.'}
                renderPagination={({ table }) => (
                    <DataTablePagination
                        table={table}
                        pageIndex={indexPage}
                        pageSize={pageSize}
                        totalRows={count ?? 0}
                        onPageIndexChange={(idx) => dispatch(fetchSetPageIndexCompanies(idx))}
                        onPageSizeChange={(size) => dispatch(fetchCompaniesPageSize(size))}
                    />
                )}
            />
        </div>
    );
}
