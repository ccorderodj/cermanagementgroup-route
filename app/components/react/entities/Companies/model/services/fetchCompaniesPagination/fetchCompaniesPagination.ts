import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import {
    getCompaniesPaginationIndexPage,
    getCompaniesPaginationPageSize,
} from '../../selectors';
import { CompaniesPaginationResult } from '../../types';
import { createQueryString, handleAsyncError } from '@/shared/lib/utils/utils';

interface IFilterParams {
    name?: string;
    lastname?: string;
}

export const fetchCompaniesPagination = createAsyncThunk<CompaniesPaginationResult, IFilterParams, ThunkConfig<string>>(
    'companies/fetchCompaniesPagination',
    async (iFilterParams, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        const { getState } = thunkApi;
        const { name, lastname } = iFilterParams;

        const pageSize = getCompaniesPaginationPageSize(getState());
        const indexPage = getCompaniesPaginationIndexPage(getState());

        const params = {
            page: indexPage + 1,
            page_size: pageSize,
        };

        const queryParams = { name, lastname };
        const requestUrl = `/companies/pagination${createQueryString(queryParams)}`;

        try {
            const response = await extra.api.get<CompaniesPaginationResult>(requestUrl, {
                params,
            });

            if (!response.data) {
                throw new Error();
            }
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
