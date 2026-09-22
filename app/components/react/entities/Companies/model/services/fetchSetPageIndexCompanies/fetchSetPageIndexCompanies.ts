import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { companiesPaginationSliceActions } from '../../slice/companiesPaginationSlice';
import { fetchCompaniesPagination } from '../fetchCompaniesPagination/fetchCompaniesPagination';

export const fetchSetPageIndexCompanies = createAsyncThunk<void, number, ThunkConfig<string>>(
    'companies/fetchSetPageIndexCompanies',
    async (pageIndex, thunkApi) => {
        const { dispatch } = thunkApi;
        dispatch(companiesPaginationSliceActions.setIndexPage(pageIndex));
        dispatch(fetchCompaniesPagination({}));
    },
);
