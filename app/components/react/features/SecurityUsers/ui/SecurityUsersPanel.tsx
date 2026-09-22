import {
    type ChangeEvent,
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
} from 'react';
import { useSelector } from 'react-redux';
import { debounce } from 'lodash';
import { PlusCircledIcon } from '@radix-ui/react-icons';
import { Search, User, X } from 'lucide-react';
import { useUser } from '@/app/providers/StoreProvider';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import {
    Button,
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    Input,
} from '@/shared/ui/shadcn/new-york';
import {
    fetchSetPageIndexUserManagementPagination,
    fetchUserManagementPagination,
    fetchUserManagementPaginationPageSize,
    getUserManagementPaginationCount,
    getUserManagementPaginationData,
    getUserManagementPaginationError,
    getUserManagementPaginationIndexPage,
    getUserManagementPaginationPageSize,
    userManagementPaginationSliceActions,
} from '@/entities/UserManagement';
import type { UserManagementEntity } from '@/entities/UserManagement';
import { DataTable, DataTablePagination } from '@/features/Common';
import { getSecurityUsersColumns } from './components/SecurityUsersColumns';
import { DataTableRowActions } from './components/data-table-row-actions';
import SecurityUserForm from './SecurityUserForm';

const DEBOUNCE_DELAY = 500;

export const SecurityUsersPanel = () => {
    const dispatch = useAppDispatch();
    const { hasUserPermission } = useUser();

    const canRead = hasUserPermission('users.read');
    const canCreate = hasUserPermission('users.create');
    const canUpdate = hasUserPermission('users.update');

    const [filterText, setFilterText] = useState('');
    const [isOpenPopup, setOpenPopup] = useState(false);
    const usersData = useSelector(getUserManagementPaginationData);
    const users = useMemo(() => usersData ?? [], [usersData]);
    const totalRows = useSelector(getUserManagementPaginationCount) || 0;
    const pageSize = useSelector(getUserManagementPaginationPageSize);
    const pageIndex = useSelector(getUserManagementPaginationIndexPage);
    const error = useSelector(getUserManagementPaginationError);

    useEffect(() => {
        if (!canRead) return;
        dispatch(fetchUserManagementPagination({}));
    }, [canRead, dispatch]);

    const handleCreated = useCallback((created: UserManagementEntity) => {
        dispatch(userManagementPaginationSliceActions.add({ index: 0, data: created }));
        setOpenPopup(false);
    }, [dispatch]);

    const openDialog = useCallback(() => setOpenPopup(true), []);
    const closeDialog = useCallback(() => setOpenPopup(false), []);

    const handleEdited = useCallback((updated: UserManagementEntity) => {
        const rowIndex = users.findIndex((row) => row.id === updated.id);
        if (rowIndex < 0) return;
        dispatch(userManagementPaginationSliceActions.update({ index: rowIndex, data: updated }));
    }, [dispatch, users]);

    const debouncedFilterSearch = useRef(
        debounce((value: string) => {
            dispatch(userManagementPaginationSliceActions.setIndexPage(0));
            dispatch(fetchUserManagementPagination({ q: value }));
        }, DEBOUNCE_DELAY),
    ).current;

    useEffect(() => {
        return () => debouncedFilterSearch.cancel();
    }, [debouncedFilterSearch]);

    const handleSearchChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
        const { value } = event.target;
        setFilterText(value);
        debouncedFilterSearch(value);
    }, [debouncedFilterSearch]);

    const clearSearch = useCallback(() => {
        setFilterText('');
        dispatch(userManagementPaginationSliceActions.setIndexPage(0));
        dispatch(fetchUserManagementPagination({ q: '' }));
    }, [dispatch]);

    const columns = useMemo(() => getSecurityUsersColumns(), []);

    if (!canRead) {
        return (
            <div className="p-4" data-testid="SecurityUsersPanelNoAccess">
                You do not have permission to view users.
            </div>
        );
    }

    return (
        <div className="h-full flex-1 flex-col space-y-4 p-8 md:flex" data-testid="SecurityUsersPanel">
            <Dialog open={isOpenPopup} onOpenChange={setOpenPopup}>
                <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-[980px] lg:max-w-[1100px]">
                    <DialogHeader>
                        <DialogTitle className="text-center">
                            <p className="inline-flex items-center gap-2">
                                <User className="h-4 w-4" />
                                Create New User
                            </p>
                        </DialogTitle>
                        <DialogDescription />
                    </DialogHeader>

                    <SecurityUserForm
                        getData={handleCreated}
                    />

                    <Button type="button" onClick={closeDialog}>
                        <X className="mr-2 h-4 w-4" />
                        Close
                    </Button>
                </DialogContent>
            </Dialog>

            <div className="flex items-center justify-between space-y-2">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">Users</h2>
                    <p className="text-muted-foreground">People with access to this account, and what each one can do.</p>
                </div>
                {canCreate && (
                    <div className="flex items-center space-x-2">
                        <Button
                            onClick={openDialog}
                            className="focus:outline-none text-primary-foreground bg-primary hover:bg-primary/90
              focus:ring-4 focus:ring-green-300 font-medium text-sm
              dark:bg-primary dark:hover:bg-primary/90"
                        >
                            Create User
                            <PlusCircledIcon className="ml-2 h-4 w-4" />
                        </Button>
                    </div>
                )}
            </div>

            <div className="space-y-4">
                {error && <div className="text-sm text-red-600">{error}</div>}
                <div className="mt-1 flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
                    <div className="relative w-full sm:w-[360px]">
                        <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <Input
                            className="h-9 pl-8 pr-8"
                            placeholder="Search users..."
                            value={filterText}
                            onChange={handleSearchChange}
                        />
                        {filterText && (
                            <button
                                type="button"
                                onClick={clearSearch}
                                className="absolute right-2.5 top-1/2 -translate-y-1/2"
                                aria-label="Clear search"
                            >
                                <X className="h-4 w-4 text-muted-foreground" />
                            </button>
                        )}
                    </div>
                </div>

                <DataTable<UserManagementEntity, unknown>
                    data={users}
                    columns={columns}
                    manualPagination
                    totalRows={totalRows}
                    state={{
                        pagination: { pageIndex, pageSize },
                    }}
                    handlers={{
                        onPaginationChange: (next) => {
                            if (next.pageIndex !== pageIndex) {
                                dispatch(fetchSetPageIndexUserManagementPagination(next.pageIndex));
                            }
                            if (next.pageSize !== pageSize) {
                                dispatch(fetchUserManagementPaginationPageSize(next.pageSize));
                            }
                        },
                    }}
                    meta={{
                        renderRowActions: ({ row }) => (
                            <DataTableRowActions
                                row={row}
                                onEdited={handleEdited}
                                disabled={!canUpdate}
                            />
                        ),
                    }}
                    renderPagination={({ table }) => (
                        <DataTablePagination
                            table={table}
                            onPageIndexChange={(idx) => dispatch(fetchSetPageIndexUserManagementPagination(idx))}
                            onPageSizeChange={(size) => dispatch(fetchUserManagementPaginationPageSize(size))}
                            pageIndex={pageIndex}
                            pageSize={pageSize}
                            totalRows={totalRows}
                        />
                    )}
                />
            </div>
        </div>
    );
};
