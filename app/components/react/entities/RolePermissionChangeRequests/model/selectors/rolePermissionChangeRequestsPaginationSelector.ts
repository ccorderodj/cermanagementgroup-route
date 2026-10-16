import { StateSchema } from '@/app/providers/StoreProvider';

export const getRolePermissionChangeRequestsPaginationData = (
    state: StateSchema,
) => state.rolePermissionChangeRequestsPagination?.data.results;
export const getRolePermissionChangeRequestsPaginationCount = (
    state: StateSchema,
) => state.rolePermissionChangeRequestsPagination?.data.count;
export const getRolePermissionChangeRequestsPaginationPageSize = (
    state: StateSchema,
) => state.rolePermissionChangeRequestsPagination?.data.page_size || 10;
export const getRolePermissionChangeRequestsPaginationIndexPage = (
    state: StateSchema,
) => state.rolePermissionChangeRequestsPagination?.data.index_page || 0;
export const getRolePermissionChangeRequestsPaginationIsLoading = (
    state: StateSchema,
) => state.rolePermissionChangeRequestsPagination?.isLoading || false;
export const getRolePermissionChangeRequestsPaginationError = (
    state: StateSchema,
) => state.rolePermissionChangeRequestsPagination?.error;
