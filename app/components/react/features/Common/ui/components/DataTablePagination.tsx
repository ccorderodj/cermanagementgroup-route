import {
    ChevronLeftIcon,
    ChevronRightIcon,
    DoubleArrowLeftIcon,
    DoubleArrowRightIcon,
} from '@radix-ui/react-icons';
import { Table } from '@tanstack/react-table';

import {
    Button,
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/shared/ui/shadcn/new-york';

interface DataTablePaginationProps<TData> {
    table: Table<TData>;

    pageIndex: number;
    pageSize: number;
    totalRows?: number;

    onPageIndexChange: (pageIndex: number) => void;
    onPageSizeChange: (pageSize: number) => void;

    pageSizes?: number[];
}

export function DataTablePagination<TData>({
    table,
    pageIndex,
    pageSize,
    totalRows,
    onPageIndexChange,
    onPageSizeChange,
    pageSizes = [10, 20, 30, 40, 50],
}: DataTablePaginationProps<TData>) {
    const pageCount = typeof totalRows === 'number' ? Math.ceil(totalRows / pageSize) : table.getPageCount();

    return (
        <div className="flex items-center justify-between px-2">
            <div className="flex-1 text-sm text-muted-foreground">
                {table.getFilteredRowModel().rows.length}
                {' '}
                row(s)
            </div>

            <div className="flex items-center space-x-6 lg:space-x-8">
                <div className="flex items-center space-x-2">
                    <p className="text-sm font-medium">Rows per page</p>
                    <Select
                        value={`${pageSize}`}
                        onValueChange={(value) => onPageSizeChange(Number(value))}
                    >
                        <SelectTrigger className="h-8 w-[70px]">
                            <SelectValue placeholder={pageSize} />
                        </SelectTrigger>
                        <SelectContent side="top">
                            {pageSizes.map((s) => (
                                <SelectItem key={s} value={`${s}`}>
                                    {s}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>

                <div className="flex w-[100px] items-center justify-center text-sm font-medium">
                    Page
                    {' '}
                    {pageIndex + 1}
                    {' '}
                    of
                    {' '}
                    {pageCount}
                </div>

                <div className="flex items-center space-x-2">
                    <Button
                        variant="outline"
                        className="hidden h-8 w-8 p-0 lg:flex"
                        onClick={() => onPageIndexChange(0)}
                        disabled={pageIndex <= 0}
                    >
                        <span className="sr-only">Go to first page</span>
                        <DoubleArrowLeftIcon className="h-4 w-4" />
                    </Button>

                    <Button
                        variant="outline"
                        className="h-8 w-8 p-0"
                        onClick={() => onPageIndexChange(Math.max(pageIndex - 1, 0))}
                        disabled={pageIndex <= 0}
                    >
                        <span className="sr-only">Go to previous page</span>
                        <ChevronLeftIcon className="h-4 w-4" />
                    </Button>

                    <Button
                        variant="outline"
                        className="h-8 w-8 p-0"
                        onClick={() => onPageIndexChange(Math.min(pageIndex + 1, pageCount - 1))}
                        disabled={pageIndex >= pageCount - 1}
                    >
                        <span className="sr-only">Go to next page</span>
                        <ChevronRightIcon className="h-4 w-4" />
                    </Button>

                    <Button
                        variant="outline"
                        className="hidden h-8 w-8 p-0 lg:flex"
                        onClick={() => onPageIndexChange(pageCount - 1)}
                        disabled={pageIndex >= pageCount - 1}
                    >
                        <span className="sr-only">Go to last page</span>
                        <DoubleArrowRightIcon className="h-4 w-4" />
                    </Button>
                </div>
            </div>
        </div>
    );
}
