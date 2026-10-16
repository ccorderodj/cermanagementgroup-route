import * as React from 'react';
import {
    ColumnDef,
    ColumnFiltersState,
    SortingState,
    VisibilityState,
    flexRender,
    getCoreRowModel,
    getFacetedRowModel,
    getFacetedUniqueValues,
    getFilteredRowModel,
    getPaginationRowModel,
    getSortedRowModel,
    useReactTable,
    Table as TanstackTable,
    TableOptions, // ✅ ADDED
} from '@tanstack/react-table';

import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/shared/ui/shadcn/new-york';

export type DataTableState = {
    sorting?: SortingState;
    columnVisibility?: VisibilityState;
    rowSelection?: Record<string, boolean>;
    columnFilters?: ColumnFiltersState;
    pagination?: { pageIndex: number; pageSize: number };
};

export type DataTableHandlers = {
    onSortingChange?: (updater: SortingState) => void;
    onColumnVisibilityChange?: (updater: VisibilityState) => void;
    onRowSelectionChange?: (updater: Record<string, boolean>) => void;
    onColumnFiltersChange?: (updater: ColumnFiltersState) => void;
    onPaginationChange?: (next: { pageIndex: number; pageSize: number }) => void;
};

type RenderToolbar<TData> = (args: { table: TanstackTable<TData> }) => React.ReactNode;
type RenderPagination<TData> = (args: { table: TanstackTable<TData> }) => React.ReactNode;

export interface DataTableProps<TData, TValue> {
    columns: ColumnDef<TData, TValue>[];
    data: TData[];

    /** If you use server-side pagination */
    manualPagination?: boolean;
    totalRows?: number; // optional, used to compute pageCount
    pageCount?: number; // optional override

    /** Controlled state from parent (or omit and it will be uncontrolled via internal state) */
    state?: DataTableState;
    handlers?: DataTableHandlers;

    /** Optional UI slots */
    renderToolbar?: RenderToolbar<TData>;
    renderPagination?: RenderPagination<TData>;

    /** ✅ ADDED: pass-through meta (for renderRowActions, row click, etc.) */
    meta?: TableOptions<TData>['meta'];

    /** Optional */
    enableRowSelection?: boolean;
    emptyMessage?: React.ReactNode;
}

export function DataTable<TData, TValue>({
    columns,
    data,

    manualPagination = false,
    totalRows,
    pageCount: pageCountOverride,

    state,
    handlers,

    renderToolbar,
    renderPagination,

    meta, // ✅ ADDED

    enableRowSelection = true,
    emptyMessage = 'No results.',
}: DataTableProps<TData, TValue>) {
    // Internal state fallback (uncontrolled mode)
    const [rowSelection, setRowSelection] = React.useState<Record<string, boolean>>({});
    const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({});
    const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);
    const [sorting, setSorting] = React.useState<SortingState>([]);
    const [pagination, setPagination] = React.useState({ pageIndex: 0, pageSize: 10 });

    const mergedState = {
        sorting: state?.sorting ?? sorting,
        columnVisibility: state?.columnVisibility ?? columnVisibility,
        rowSelection: state?.rowSelection ?? rowSelection,
        columnFilters: state?.columnFilters ?? columnFilters,
        pagination: state?.pagination ?? pagination,
    };

    const resolvedPageCount = pageCountOverride
        ?? (typeof totalRows === 'number'
            ? Math.ceil(totalRows / mergedState.pagination.pageSize)
            : undefined);

    const table = useReactTable({
        data,
        columns,

        meta, // ✅ ADDED

        state: mergedState,

        enableRowSelection,
        manualPagination,
        pageCount: resolvedPageCount,

        onRowSelectionChange: (updater) => {
            const next = typeof updater === 'function' ? updater(mergedState.rowSelection) : updater;
            handlers?.onRowSelectionChange?.(next);
            if (!state?.rowSelection) setRowSelection(next);
        },

        onSortingChange: (updater) => {
            const next = typeof updater === 'function' ? updater(mergedState.sorting) : updater;
            handlers?.onSortingChange?.(next);
            if (!state?.sorting) setSorting(next);
        },

        onColumnFiltersChange: (updater) => {
            const next = typeof updater === 'function' ? updater(mergedState.columnFilters) : updater;
            handlers?.onColumnFiltersChange?.(next);
            if (!state?.columnFilters) setColumnFilters(next);
        },

        onColumnVisibilityChange: (updater) => {
            const next = typeof updater === 'function' ? updater(mergedState.columnVisibility) : updater;
            handlers?.onColumnVisibilityChange?.(next);
            if (!state?.columnVisibility) setColumnVisibility(next);
        },

        // TanStack's pagination onChange uses updater signatures; we normalize to plain object.
        onPaginationChange: (updater) => {
            const next = typeof updater === 'function' ? updater(mergedState.pagination) : updater;
            handlers?.onPaginationChange?.(next);
            if (!state?.pagination) setPagination(next);
        },

        getCoreRowModel: getCoreRowModel(),
        getFilteredRowModel: getFilteredRowModel(),
        getPaginationRowModel: getPaginationRowModel(),
        getSortedRowModel: getSortedRowModel(),
        getFacetedRowModel: getFacetedRowModel(),
        getFacetedUniqueValues: getFacetedUniqueValues(),
    });

    return (
        <div className="space-y-4">
            {renderToolbar?.({ table })}

            {/* `overflow-x-auto`: una tabla ancha se desplaza DENTRO de su
                marco. Sin esto empujaba la maquetacion entera y la pagina se
                desplazaba en horizontal —visible en cuanto la ventana baja de
                los ~900px—, que es lo que el requisito de responsive prohibe. */}
            <div className="overflow-x-auto rounded-md border">
                <Table>
                    <TableHeader>
                        {table.getHeaderGroups().map((headerGroup) => (
                            <TableRow key={headerGroup.id}>
                                {headerGroup.headers.map((header) => (
                                    <TableHead key={header.id} colSpan={header.colSpan}>
                                        {header.isPlaceholder
                                            ? null
                                            : flexRender(header.column.columnDef.header, header.getContext())}
                                    </TableHead>
                                ))}
                            </TableRow>
                        ))}
                    </TableHeader>

                    <TableBody>
                        {table.getRowModel().rows?.length ? (
                            table.getRowModel().rows.map((row) => (
                                <TableRow key={row.id} data-state={row.getIsSelected() && 'selected'}>
                                    {row.getVisibleCells().map((cell) => (
                                        <TableCell key={cell.id}>
                                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                        </TableCell>
                                    ))}
                                </TableRow>
                            ))
                        ) : (
                            <TableRow>
                                <TableCell colSpan={columns.length} className="h-24 text-center">
                                    {emptyMessage}
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </div>

            {renderPagination?.({ table })}
        </div>
    );
}
