import { StateSchema } from '@/app/providers/StoreProvider';

export const getCompaniesPaginationData = (state: StateSchema) => state.companiesPagination?.data.results;
export const getCompaniesPaginationNext = (state: StateSchema) => state.companiesPagination?.data.next || false;
export const getCompaniesPaginationPrevious = (state: StateSchema) => state.companiesPagination?.data.previous || false;
export const getCompaniesPaginationCount = (state: StateSchema) => state.companiesPagination?.data.count;
export const getCompaniesPaginationPageSize = (state: StateSchema) => state.companiesPagination?.data.page_size || 10;
export const getCompaniesPaginationIndexPage = (state: StateSchema) => state.companiesPagination?.data.index_page || 0;
export const getCompaniesPaginationIsLoading = (state: StateSchema) => state.companiesPagination?.isLoading || false;
export const getCompaniesPaginationError = (state: StateSchema) => state.companiesPagination?.error;

export const getCompaniesData = (state: StateSchema) => state.companies?.data;
export const getCompaniesIsLoading = (state: StateSchema) => state.companies?.isLoading || false;
export const getCompaniesError = (state: StateSchema) => state.companiesPagination?.error;

export const getCompanyId = (state: StateSchema) => state.companies.companyId;
