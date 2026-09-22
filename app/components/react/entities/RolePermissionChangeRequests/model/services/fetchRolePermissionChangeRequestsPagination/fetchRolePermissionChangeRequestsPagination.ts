import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import {
    getRolePermissionChangeRequestsPaginationIndexPage,
    getRolePermissionChangeRequestsPaginationPageSize,
} from '../../selectors';
import { rolePermissionChangeRequestsPaginationSliceActions } from '../../slice';
import { RolePermissionChangeRequestPaginationResult } from '../../types';

interface IFilterParams {
    role_id?: number;
    requested_by_user_id?: number;
    reviewed_by_user_id?: number;
    is_active?: boolean;
}

export const fetchRolePermissionChangeRequestsPagination = createAsyncThunk<
RolePermissionChangeRequestPaginationResult,
IFilterParams,
ThunkConfig<string>
>(
    'rolePermissionChangeRequests/fetchRolePermissionChangeRequestsPagination',
    async (filters, thunkApi) => {
        const { extra, getState, rejectWithValue } = thunkApi;

        const pageSize = getRolePermissionChangeRequestsPaginationPageSize(getState());
        const indexPage = getRolePermissionChangeRequestsPaginationIndexPage(getState());

        const params: Record<string, string | number | boolean> = {
            page: indexPage + 1,
            page_size: pageSize,
        };

        if (filters.role_id) params.role_id = filters.role_id;
        if (filters.requested_by_user_id) params.requested_by_user_id = filters.requested_by_user_id;
        if (filters.reviewed_by_user_id) params.reviewed_by_user_id = filters.reviewed_by_user_id;
        if (filters.is_active !== undefined) params.is_active = filters.is_active;

        try {
            const response = await extra.api.get<RolePermissionChangeRequestPaginationResult>(
                '/rolepermissionsapprovals/pagination',
                { params },
            );
            if (!response.data) {
                throw new Error();
            }
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);

export const fetchSetPageIndexRolePermissionChangeRequestsPagination = createAsyncThunk<
void,
number,
ThunkConfig<string>
>(
    'rolePermissionChangeRequests/fetchSetPageIndexRolePermissionChangeRequestsPagination',
    async (pageIndex, thunkApi) => {
        const { dispatch } = thunkApi;
        dispatch(rolePermissionChangeRequestsPaginationSliceActions.setIndexPage(pageIndex));
        dispatch(fetchRolePermissionChangeRequestsPagination({}));
    },
);

export const fetchRolePermissionChangeRequestsPaginationPageSize = createAsyncThunk<
void,
number,
ThunkConfig<string>
>(
    'rolePermissionChangeRequests/fetchRolePermissionChangeRequestsPaginationPageSize',
    async (pageSize, thunkApi) => {
        const { dispatch } = thunkApi;
        dispatch(rolePermissionChangeRequestsPaginationSliceActions.setPageSize(pageSize));
        dispatch(rolePermissionChangeRequestsPaginationSliceActions.setIndexPage(0));
        dispatch(fetchRolePermissionChangeRequestsPagination({}));
    },
);
