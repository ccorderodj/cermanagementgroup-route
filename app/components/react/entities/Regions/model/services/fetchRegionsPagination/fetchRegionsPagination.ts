import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import {
    getRegionsPaginationIndexPage,
    getRegionsPaginationPageSize,
} from '../../selectors';
import { RegionsPaginationResult } from '../../types';
import { createQueryString, handleAsyncError } from '@/shared/lib/utils/utils';

interface IFilterParams {
    name?: string;
    lastname?: string;
}

export const fetchRegionsPagination = createAsyncThunk<RegionsPaginationResult, IFilterParams, ThunkConfig<string>>(
    'regions/fetchRegionsPagination',
    async (iFilterParams, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        const { getState } = thunkApi;
        const { name, lastname } = iFilterParams;

        const pageSize = getRegionsPaginationPageSize(getState());
        const indexPage = getRegionsPaginationIndexPage(getState());

        const params = {
            page: indexPage + 1,
            page_size: pageSize,
        };

        const queryParams = { name, lastname };
        const requestUrl = `/regions/pagination${createQueryString(queryParams)}`;

        try {
            const response = await extra.api.get<RegionsPaginationResult>(requestUrl, {
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
