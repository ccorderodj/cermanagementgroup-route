import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import {
    getPermissionsPaginationIndexPage,
    getPermissionsPaginationPageSize,
} from '../../selectors';
import { permissionsPaginationSliceActions } from '../../slice';
import { PermissionPaginationResult } from '../../types';
import { handleAsyncError } from '@/shared/lib/utils/utils';

interface IFilterParams {
    name?: string;
}

export const fetchPermissionsPagination = createAsyncThunk<PermissionPaginationResult, IFilterParams, ThunkConfig<string>>(
    'permissions/fetchPermissionsPagination',
    async (filters, thunkApi) => {
        const { extra, getState, rejectWithValue } = thunkApi;

        const pageSize = getPermissionsPaginationPageSize(getState());
        const indexPage = getPermissionsPaginationIndexPage(getState());

        const params: Record<string, string | number> = {
            page: indexPage + 1,
            page_size: pageSize,
        };
        if (filters.name) {
            params.name = filters.name;
        }

        try {
            const response = await extra.api.get<PermissionPaginationResult>('/permissions/pagination', { params });
            if (!response.data) {
                throw new Error();
            }
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);

export const fetchSetPageIndexPermissionsPagination = createAsyncThunk<void, number, ThunkConfig<string>>(
    'permissions/fetchSetPageIndexPermissionsPagination',
    async (pageIndex, thunkApi) => {
        const { dispatch } = thunkApi;
        dispatch(permissionsPaginationSliceActions.setIndexPage(pageIndex));
        dispatch(fetchPermissionsPagination({}));
    },
);

export const fetchPermissionsPaginationPageSize = createAsyncThunk<void, number, ThunkConfig<string>>(
    'permissions/fetchPermissionsPaginationPageSize',
    async (pageSize, thunkApi) => {
        const { dispatch } = thunkApi;
        dispatch(permissionsPaginationSliceActions.setPageSize(pageSize));
        dispatch(permissionsPaginationSliceActions.setIndexPage(0));
        dispatch(fetchPermissionsPagination({}));
    },
);
