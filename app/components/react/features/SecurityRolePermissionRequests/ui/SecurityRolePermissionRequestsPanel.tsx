import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSelector } from 'react-redux';
import { useUser } from '@/app/providers/StoreProvider';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import {
    fetchRolePermissionChangeRequestsPagination,
    fetchRolePermissionChangeRequestsPaginationPageSize,
    fetchSetPageIndexRolePermissionChangeRequestsPagination,
    getRolePermissionChangeRequestsPaginationCount,
    getRolePermissionChangeRequestsPaginationData,
    getRolePermissionChangeRequestsPaginationError,
    getRolePermissionChangeRequestsPaginationIndexPage,
    getRolePermissionChangeRequestsPaginationPageSize,
    RolePermissionChangeRequestEntity,
} from '@/entities/RolePermissionChangeRequests';
import { DataTable, DataTablePagination } from '@/features/Common';
import { getSecurityRolePermissionRequestsColumns } from './components/SecurityRolePermissionRequestsColumns';
import { ReviewRowActions } from './components/ReviewRowActions';

export const SecurityRolePermissionRequestsPanel = () => {
    const dispatch = useAppDispatch();
    const { hasUserPermission } = useUser();

    const canRead = hasUserPermission('rolepermissions.read');
    const [localError, setLocalError] = useState('');

    const rowsData = useSelector(getRolePermissionChangeRequestsPaginationData);
    const rows = useMemo(() => rowsData ?? [], [rowsData]);
    const totalRows = useSelector(getRolePermissionChangeRequestsPaginationCount) || 0;
    const pageSize = useSelector(getRolePermissionChangeRequestsPaginationPageSize);
    const pageIndex = useSelector(getRolePermissionChangeRequestsPaginationIndexPage);
    const error = useSelector(getRolePermissionChangeRequestsPaginationError);

    useEffect(() => {
        if (!canRead) return;
        dispatch(fetchRolePermissionChangeRequestsPagination({}));
    }, [canRead, dispatch]);

    const columns = useMemo(() => getSecurityRolePermissionRequestsColumns(), []);

    const reload = useCallback(() => {
        setLocalError('');
        dispatch(fetchRolePermissionChangeRequestsPagination({}));
    }, [dispatch]);

    if (!canRead) {
        return <div className="p-4">You do not have permission to view role-permission requests.</div>;
    }

    return (
        <div className="h-full flex-1 flex-col space-y-4 p-8 md:flex" data-testid="SecurityRolePermissionRequestsPanel">
            <div className="flex items-center justify-between space-y-2">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">Permission Requests</h2>
                    <p className="text-muted-foreground">
                        Permission changes waiting for review. Only management roles can
                        approve, and never the person who submitted the request.
                    </p>
                </div>
            </div>

            <div className="space-y-4">
                {(error || localError) && (
                    <div className="text-sm text-destructive">{error || localError}</div>
                )}

                <DataTable<RolePermissionChangeRequestEntity, unknown>
                    data={rows}
                    columns={columns}
                    manualPagination
                    totalRows={totalRows}
                    state={{
                        pagination: { pageIndex, pageSize },
                    }}
                    handlers={{
                        onPaginationChange: (next) => {
                            if (next.pageIndex !== pageIndex) {
                                dispatch(fetchSetPageIndexRolePermissionChangeRequestsPagination(next.pageIndex));
                            }
                            if (next.pageSize !== pageSize) {
                                dispatch(fetchRolePermissionChangeRequestsPaginationPageSize(next.pageSize));
                            }
                        },
                    }}
                    meta={{
                        renderRowActions: ({ row }) => (
                            <ReviewRowActions
                                row={row}
                                onReviewed={reload}
                                onError={setLocalError}
                            />
                        ),
                    }}
                    renderPagination={({ table }) => (
                        <DataTablePagination
                            table={table}
                            onPageIndexChange={(idx) => dispatch(fetchSetPageIndexRolePermissionChangeRequestsPagination(idx))}
                            onPageSizeChange={(size) => dispatch(fetchRolePermissionChangeRequestsPaginationPageSize(size))}
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
