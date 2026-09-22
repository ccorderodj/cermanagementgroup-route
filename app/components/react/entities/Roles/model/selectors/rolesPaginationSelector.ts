import { StateSchema } from '@/app/providers/StoreProvider';

export const getRolesPaginationData = (state: StateSchema) => state.rolesPagination?.data.results;
export const getRolesPaginationCount = (state: StateSchema) => state.rolesPagination?.data.count;
export const getRolesPaginationPageSize = (state: StateSchema) => state.rolesPagination?.data.page_size || 10;
export const getRolesPaginationIndexPage = (state: StateSchema) => state.rolesPagination?.data.index_page || 0;
export const getRolesPaginationIsLoading = (state: StateSchema) => state.rolesPagination?.isLoading || false;
export const getRolesPaginationError = (state: StateSchema) => state.rolesPagination?.error;
