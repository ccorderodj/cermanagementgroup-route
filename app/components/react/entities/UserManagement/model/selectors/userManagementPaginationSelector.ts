import { StateSchema } from '@/app/providers/StoreProvider';

export const getUserManagementPaginationData = (state: StateSchema) => state.userManagementPagination?.data.results;
export const getUserManagementPaginationCount = (state: StateSchema) => state.userManagementPagination?.data.count;
export const getUserManagementPaginationPageSize = (state: StateSchema) => state.userManagementPagination?.data.page_size || 10;
export const getUserManagementPaginationIndexPage = (state: StateSchema) => state.userManagementPagination?.data.index_page || 0;
export const getUserManagementPaginationIsLoading = (state: StateSchema) => state.userManagementPagination?.isLoading || false;
export const getUserManagementPaginationError = (state: StateSchema) => state.userManagementPagination?.error;
