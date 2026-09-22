import { StateSchema } from '@/app/providers/StoreProvider';

export const getPermissionsPaginationData = (state: StateSchema) => state.permissionsPagination?.data.results;
export const getPermissionsPaginationCount = (state: StateSchema) => state.permissionsPagination?.data.count;
export const getPermissionsPaginationPageSize = (state: StateSchema) => state.permissionsPagination?.data.page_size || 10;
export const getPermissionsPaginationIndexPage = (state: StateSchema) => state.permissionsPagination?.data.index_page || 0;
export const getPermissionsPaginationIsLoading = (state: StateSchema) => state.permissionsPagination?.isLoading || false;
export const getPermissionsPaginationError = (state: StateSchema) => state.permissionsPagination?.error;
