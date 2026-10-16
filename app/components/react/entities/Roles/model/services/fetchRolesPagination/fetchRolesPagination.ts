import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import {
    getRolesPaginationIndexPage,
    getRolesPaginationPageSize,
} from '../../selectors';
import { rolesPaginationSliceActions } from '../../slice';
import { RolePaginationResult } from '../../types';
import { handleAsyncError } from '@/shared/lib/utils/utils';

interface IFilterParams {
    name?: string;
}

export const fetchRolesPagination = createAsyncThunk<RolePaginationResult, IFilterParams, ThunkConfig<string>>(
    'roles/fetchRolesPagination',
    async (filters, thunkApi) => {
        const { extra, getState, rejectWithValue } = thunkApi;

        const pageSize = getRolesPaginationPageSize(getState());
        const indexPage = getRolesPaginationIndexPage(getState());

        const params: Record<string, string | number> = {
            page: indexPage + 1,
            page_size: pageSize,
        };
        if (filters.name) {
            params.name = filters.name;
        }

        try {
            const response = await extra.api.get<RolePaginationResult>('/roles/pagination', { params });
            if (!response.data) {
                throw new Error();
            }
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);

export const fetchSetPageIndexRolesPagination = createAsyncThunk<void, number, ThunkConfig<string>>(
    'roles/fetchSetPageIndexRolesPagination',
    async (pageIndex, thunkApi) => {
        const { dispatch } = thunkApi;
        dispatch(rolesPaginationSliceActions.setIndexPage(pageIndex));
        dispatch(fetchRolesPagination({}));
    },
);

export const fetchRolesPaginationPageSize = createAsyncThunk<void, number, ThunkConfig<string>>(
    'roles/fetchRolesPaginationPageSize',
    async (pageSize, thunkApi) => {
        const { dispatch } = thunkApi;
        dispatch(rolesPaginationSliceActions.setPageSize(pageSize));
        dispatch(rolesPaginationSliceActions.setIndexPage(0));
        dispatch(fetchRolesPagination({}));
    },
);
