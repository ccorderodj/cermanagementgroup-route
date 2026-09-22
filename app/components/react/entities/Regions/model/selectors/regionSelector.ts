import { StateSchema } from '@/app/providers/StoreProvider';

export const getRegionsData = (state: StateSchema) => state.regions?.data;
export const getRegionsIsLoading = (state: StateSchema) => state.regions?.isLoading || false;
export const getRegionsError = (state: StateSchema) => state.regions?.error;

export const getRegionIds = (state: StateSchema) => state.regions?.region_ids ?? [];

export const getRegionsPaginationData = (state: StateSchema) => state.regionsPagination?.data.results;
export const getRegionsPaginationNext = (state: StateSchema) => state.regionsPagination?.data.next || false;
export const getRegionsPaginationPrevious = (state: StateSchema) => state.regionsPagination?.data.previous || false;
export const getRegionsPaginationCount = (state: StateSchema) => state.regionsPagination?.data.count;
export const getRegionsPaginationPageSize = (state: StateSchema) => state.regionsPagination?.data.page_size || 10;
export const getRegionsPaginationIndexPage = (state: StateSchema) => state.regionsPagination?.data.index_page || 0;
export const getRegionsPaginationIsLoading = (state: StateSchema) => state.regionsPagination?.isLoading || false;
export const getRegionsPaginationError = (state: StateSchema) => state.regionsPagination?.error;

export const getRegionId = (state: StateSchema) => state.regions.regionId;
