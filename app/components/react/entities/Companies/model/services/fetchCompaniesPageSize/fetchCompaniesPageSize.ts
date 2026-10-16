import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { companiesPaginationSliceActions } from '../../slice/companiesPaginationSlice';
import { fetchCompaniesPagination } from '../fetchCompaniesPagination/fetchCompaniesPagination';

export const fetchCompaniesPageSize = createAsyncThunk<void, number, ThunkConfig<string>>(
    'companies/fetchCompaniesPageSize',
    async (pageSize, thunkApi) => {
        const { dispatch } = thunkApi;
        dispatch(companiesPaginationSliceActions.setPageSize(pageSize));
        dispatch(companiesPaginationSliceActions.setIndexPage(0));
        dispatch(fetchCompaniesPagination({}));
    },
);
