import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import {
    getUserManagementPaginationIndexPage,
    getUserManagementPaginationPageSize,
} from '../../selectors';
import { userManagementPaginationSliceActions } from '../../slice';
import { UserManagementPaginationResult } from '../../types';
import { handleAsyncError } from '@/shared/lib/utils/utils';

interface IFilterParams {
    q?: string;
}

export const fetchUserManagementPagination = createAsyncThunk<UserManagementPaginationResult, IFilterParams, ThunkConfig<string>>(
    'userManagement/fetchUserManagementPagination',
    async (filters, thunkApi) => {
        const { extra, getState, rejectWithValue } = thunkApi;

        const pageSize = getUserManagementPaginationPageSize(getState());
        const indexPage = getUserManagementPaginationIndexPage(getState());

        const params: Record<string, string | number> = {
            page: indexPage + 1,
            page_size: pageSize,
        };
        if (filters.q) {
            params.q = filters.q;
        }

        try {
            const response = await extra.api.get<UserManagementPaginationResult>('/users/pagination', { params });
            if (!response.data) {
                throw new Error();
            }
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);

export const fetchSetPageIndexUserManagementPagination = createAsyncThunk<void, number, ThunkConfig<string>>(
    'userManagement/fetchSetPageIndexUserManagementPagination',
    async (pageIndex, thunkApi) => {
        const { dispatch } = thunkApi;
        dispatch(userManagementPaginationSliceActions.setIndexPage(pageIndex));
        dispatch(fetchUserManagementPagination({}));
    },
);

export const fetchUserManagementPaginationPageSize = createAsyncThunk<void, number, ThunkConfig<string>>(
    'userManagement/fetchUserManagementPaginationPageSize',
    async (pageSize, thunkApi) => {
        const { dispatch } = thunkApi;
        dispatch(userManagementPaginationSliceActions.setPageSize(pageSize));
        dispatch(userManagementPaginationSliceActions.setIndexPage(0));
        dispatch(fetchUserManagementPagination({}));
    },
);
